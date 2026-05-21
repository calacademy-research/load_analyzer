#!/usr/bin/env python3
"""Collects Slurm job data via sacct and stores in MySQL for allocation efficiency analysis."""
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from app.config import DB_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/slurm_collector.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

SLURM_HOST = 'ibss-genomics'
SLURM_USER = 'loadmon'
LOOKBACK_DAYS = 1  # per-run window; run hourly so overlapping windows keep data fresh


def get_engine():
    return create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    )


def ensure_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS slurm_jobs (
                job_id VARCHAR(30) NOT NULL,
                username VARCHAR(50) NOT NULL,
                partition_name VARCHAR(50),
                alloc_cpus INT NOT NULL DEFAULT 0,
                req_mem_gb DOUBLE NOT NULL DEFAULT 0,
                max_rss_gb DOUBLE NOT NULL DEFAULT 0,
                elapsed_seconds INT NOT NULL DEFAULT 0,
                state VARCHAR(30),
                node_list VARCHAR(200),
                submit_time DATETIME,
                start_time DATETIME,
                end_time DATETIME,
                PRIMARY KEY (job_id),
                INDEX idx_slurm_user (username),
                INDEX idx_slurm_time (end_time)
            )
        """))


def parse_mem(mem_str):
    """Parse Slurm memory string (e.g. '128G', '4096M', '797402660K') to GB."""
    if not mem_str:
        return 0.0
    mem_str = mem_str.strip()
    try:
        if mem_str.endswith('K'):
            return float(mem_str[:-1]) / 1048576  # KB to GB
        elif mem_str.endswith('M'):
            return float(mem_str[:-1]) / 1024
        elif mem_str.endswith('G'):
            return float(mem_str[:-1])
        elif mem_str.endswith('T'):
            return float(mem_str[:-1]) * 1024
        else:
            return float(mem_str) / 1048576  # assume KB
    except (ValueError, TypeError):
        return 0.0


def parse_elapsed(elapsed_str):
    """Parse Slurm elapsed time (e.g. '2-06:07:26', '00:05:00') to seconds."""
    if not elapsed_str:
        return 0
    try:
        days = 0
        if '-' in elapsed_str:
            day_part, time_part = elapsed_str.split('-', 1)
            days = int(day_part)
        else:
            time_part = elapsed_str
        parts = time_part.split(':')
        hours = int(parts[0]) if len(parts) > 0 else 0
        mins = int(parts[1]) if len(parts) > 1 else 0
        secs = int(parts[2]) if len(parts) > 2 else 0
        return days * 86400 + hours * 3600 + mins * 60 + secs
    except (ValueError, IndexError):
        return 0


def collect_jobs():
    engine = get_engine()
    ensure_table(engine)

    # Query recent jobs (small window keeps the sacct --allusers query fast)
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')

    sacct_cmd = (
        f"ssh -i /admin/monitor-keys/monitor_ed25519 -o StrictHostKeyChecking=accept-new {SLURM_USER}@{SLURM_HOST} "
        f"\"sacct --starttime={start_date} --allusers --noheader -P "
        f"--format=JobID,User,Partition,AllocCPUS,ReqMem,MaxRSS,Elapsed,State,NodeList,Submit,Start,End\""
    )

    logger.info(f"Running: {sacct_cmd}")
    result = subprocess.run(sacct_cmd, shell=True, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error(f"sacct failed: {result.stderr}")
        return

    lines = result.stdout.strip().split('\n')
    # First pass: peak MaxRSS for a job lives on its step rows (.batch/.0/...), not the alloc row
    step_maxrss = {}
    for line in lines:
        if not line:
            continue
        sf = line.split('|')
        if len(sf) < 12 or '.' not in sf[0]:
            continue
        parent = sf[0].split('.')[0]
        rss = parse_mem(sf[5])
        if rss > step_maxrss.get(parent, 0):
            step_maxrss[parent] = rss

    rows = []
    for line in lines:
        if not line:
            continue
        fields = line.split('|')
        if len(fields) < 12:
            continue

        job_id = fields[0]
        # Skip sub-job steps (e.g. "1234.batch", "1234.0") — only keep main job entries
        if '.' in job_id:
            continue
        # Skip array sub-jobs notation like "1234_[5-10]" but keep individual "1234_5"
        if not fields[1]:  # sub-steps have empty user
            continue

        username = fields[1]
        partition = fields[2] or None
        alloc_cpus = int(fields[3]) if fields[3] else 0
        req_mem_gb = parse_mem(fields[4])
        max_rss_gb = max(parse_mem(fields[5]), step_maxrss.get(job_id, 0))
        elapsed_secs = parse_elapsed(fields[6])
        state = fields[7].split(' ')[0] if fields[7] else None  # Remove "by XXXX" suffix

        node_list = fields[8] or None
        _bad_dt = ('', 'Unknown', 'None')
        submit_time = fields[9] if fields[9] not in _bad_dt else None
        start_time = fields[10] if fields[10] not in _bad_dt else None
        end_time = fields[11] if fields[11] not in _bad_dt else None

        rows.append({
            'job_id': job_id,
            'username': username,
            'partition_name': partition,
            'alloc_cpus': alloc_cpus,
            'req_mem_gb': round(req_mem_gb, 2),
            'max_rss_gb': round(max_rss_gb, 2),
            'elapsed_seconds': elapsed_secs,
            'state': state,
            'node_list': node_list,
            'submit_time': submit_time,
            'start_time': start_time,
            'end_time': end_time,
        })

    if not rows:
        logger.info("No jobs found")
        return

    logger.info(f"Collected {len(rows)} jobs")

    # Upsert rows in batches (executemany) to handle high row counts
    stmt = text("""
        INSERT INTO slurm_jobs (job_id, username, partition_name, alloc_cpus,
            req_mem_gb, max_rss_gb, elapsed_seconds, state, node_list,
            submit_time, start_time, end_time)
        VALUES (:job_id, :username, :partition_name, :alloc_cpus,
            :req_mem_gb, :max_rss_gb, :elapsed_seconds, :state, :node_list,
            :submit_time, :start_time, :end_time)
        ON DUPLICATE KEY UPDATE
            max_rss_gb = VALUES(max_rss_gb),
            elapsed_seconds = VALUES(elapsed_seconds),
            state = VALUES(state),
            end_time = VALUES(end_time)
    """)
    CHUNK = 1000
    with engine.begin() as conn:
        for i in range(0, len(rows), CHUNK):
            conn.execute(stmt, rows[i:i + CHUNK])

    logger.info(f"Wrote {len(rows)} jobs to slurm_jobs")


if __name__ == "__main__":
    collect_jobs()
