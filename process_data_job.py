#!/usr/bin/env python3
"""Cron job: reads raw processes from MySQL, computes cpu_norm, writes to load_summary table."""
import logging
import sys
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from app.config import DB_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/load_analyzer_data_processor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_engine():
    return create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    )


def ensure_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS load_summary (
                snapshot_datetime DATETIME NOT NULL,
                host VARCHAR(20) NOT NULL,
                username VARCHAR(50) NOT NULL,
                comm VARCHAR(100) NOT NULL,
                cpu_norm DOUBLE NOT NULL DEFAULT 0,
                rss DOUBLE NOT NULL DEFAULT 0,
                pss DOUBLE NOT NULL DEFAULT 0,
                PRIMARY KEY (snapshot_datetime, host, username, comm),
                INDEX idx_host_time (host, snapshot_datetime)
            )
        """))
        # Add pss column if it doesn't exist (for existing tables)
        try:
            conn.execute(text("ALTER TABLE load_summary ADD COLUMN pss DOUBLE NOT NULL DEFAULT 0 AFTER rss"))
            logger.info("Added pss column to load_summary")
        except Exception:
            pass  # Column already exists
        # Per-process peak-stats table backing the Processes tab (avoids GROUP BY
        # over the 200M+ row processes table on every request).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS process_summary (
                host VARCHAR(20) NOT NULL,
                pid INT NOT NULL,
                username VARCHAR(50) NOT NULL,
                comm VARCHAR(100) NOT NULL,
                args VARCHAR(500),
                peak_rss DOUBLE NOT NULL DEFAULT 0,
                peak_pss DOUBLE NOT NULL DEFAULT 0,
                peak_mem DOUBLE AS (GREATEST(peak_rss, peak_pss)) STORED,
                max_cputimes DOUBLE NOT NULL DEFAULT 0,
                max_thcount INT NOT NULL DEFAULT 0,
                max_etimes DOUBLE NOT NULL DEFAULT 0,
                first_seen DATETIME,
                last_seen DATETIME,
                snapshot_count INT NOT NULL DEFAULT 0,
                PRIMARY KEY (host, pid, username, comm),
                INDEX idx_ps_last_seen (last_seen),
                INDEX idx_ps_user_last (username, last_seen),
                INDEX idx_ps_host_last (host, last_seen),
                INDEX idx_ps_peak (peak_mem),
                INDEX idx_ps_user_peak (username, peak_mem),
                INDEX idx_ps_host_peak (host, peak_mem)
            )
        """))
        # Migrate existing process_summary: add peak_mem generated column + indexes
        if not conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() "
            "AND table_name='process_summary' AND column_name='peak_mem'"
        )).scalar():
            conn.execute(text("ALTER TABLE process_summary ADD COLUMN peak_mem DOUBLE AS (GREATEST(peak_rss, peak_pss)) STORED"))
            conn.execute(text("ALTER TABLE process_summary ADD INDEX idx_ps_peak (peak_mem), "
                              "ADD INDEX idx_ps_user_peak (username, peak_mem), ADD INDEX idx_ps_host_peak (host, peak_mem)"))


def update_process_summary(engine):
    """Upsert the last day's per-process peak stats into process_summary and prune
    rows older than the longest dashboard window (90d). Idempotent (GREATEST/LEAST)."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO process_summary (host,pid,username,comm,args,peak_rss,peak_pss,
                max_cputimes,max_thcount,max_etimes,first_seen,last_seen,snapshot_count)
            SELECT host,pid,username,comm, SUBSTRING(MAX(args),1,500),
                   MAX(rss), MAX(pss), MAX(cputimes), MAX(thcount), MAX(etimes),
                   MIN(snapshot_datetime), MAX(snapshot_datetime), COUNT(*)
            FROM processes WHERE snapshot_datetime >= NOW() - INTERVAL 1 DAY
            GROUP BY host,pid,username,comm
            ON DUPLICATE KEY UPDATE
                args=VALUES(args),
                peak_rss=GREATEST(peak_rss,VALUES(peak_rss)),
                peak_pss=GREATEST(peak_pss,VALUES(peak_pss)),
                max_cputimes=GREATEST(max_cputimes,VALUES(max_cputimes)),
                max_thcount=GREATEST(max_thcount,VALUES(max_thcount)),
                max_etimes=GREATEST(max_etimes,VALUES(max_etimes)),
                first_seen=LEAST(first_seen,VALUES(first_seen)),
                last_seen=GREATEST(last_seen,VALUES(last_seen)),
                snapshot_count=GREATEST(snapshot_count,VALUES(snapshot_count))
        """))
        conn.execute(text("DELETE FROM process_summary WHERE last_seen < NOW() - INTERVAL 90 DAY"))
    logger.info("Updated process_summary (1-day upsert + 90d prune)")


def process_data():
    try:
        engine = get_engine()
        ensure_table(engine)
        update_process_summary(engine)

        start = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        end = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Processing data from {start} to {end}")

        df = pd.read_sql(
            f"SELECT * FROM processes WHERE snapshot_datetime BETWEEN '{start}' AND '{end}'",
            con=engine
        )
        if df.empty:
            logger.info("No data to process")
            return

        # Compute cpu_norm: normalized CPU usage (cores consumed per second)
        # Filter out system/service accounts — only show real user load
        exclude_users = {
            'root', 'daemon', 'bin', 'sys', 'sync', 'games', 'man', 'lp', 'mail',
            'news', 'uucp', 'proxy', 'www-data', 'backup', 'list', 'irc', 'gnats',
            'nobody', 'systemd-network', 'systemd-resolve', 'syslog', 'messagebus',
            '_apt', 'lxd', 'uuidd', 'dnsmasq', 'landscape', 'pollinate', 'sshd',
            'sssd', 'statd', 'ntp', 'nagios', 'scan', 'sophosav', 'zabbix', 'tss',
            'tcpdump', '_rpc', 'usbmux', 'avahi', 'netdata', 'gdm',
            'gnome-remote-desktop', 'ntpsec', 'nx', 'polkitd', 'rstudio-server',
            'sophos-spl-av', 'sophos-spl-local', 'sophos-spl-updatescheduler',
            'sophos-spl-user',
            'rtkit',
            'munge',
        }
        df = df[~df['username'].isin(exclude_users)]
        # Also exclude usernames that look like system accounts (sophos-*, etc.)
        df = df[~df['username'].str.startswith('sophos-')]
        # Exclude numeric-only usernames (unresolved UIDs)
        df = df[~df['username'].str.match(r'^\d+$')]
        if df.empty:
            logger.info("No user data after filtering system accounts")
            return

        df = df.sort_values(by='snapshot_datetime', ascending=True)
        df['rss'] = (df['rss'] / 1000000).round(4)  # KB to GB
        if 'pss' in df.columns:
            df['pss'] = (df['pss'] / 1000000).round(4)  # KB to GB
        else:
            df['pss'] = 0.0
        df['cpu_diff'] = (df['cputimes'] - df.groupby(['host', 'pid'])['cputimes'].shift()).fillna(0)
        df['seconds_diff'] = (df['snapshot_time_epoch'] -
                              df.groupby(['host', 'pid'])['snapshot_time_epoch'].shift()).fillna(0)
        df['cpu_norm'] = (df['cpu_diff'].div(df['seconds_diff'])).fillna(0).replace([float('inf'), float('-inf')], 0)
        df = df[(df['cpu_norm'] > 0) & (df['cpu_norm'] < 10000)]  # Filter out unreasonable values

        # Aggregate to 5-min buckets per (host, username, comm)
        summary = df.groupby([
            pd.Grouper(key='snapshot_datetime', freq='5min'),
            'host', 'username', 'comm'
        ]).agg(
            cpu_norm=('cpu_norm', 'sum'),
            rss=('rss', 'sum'),
            pss=('pss', 'sum'),
        ).reset_index()

        summary = summary[(summary['cpu_norm'] > 0) | (summary['rss'] > 0)]
        summary['cpu_norm'] = summary['cpu_norm'].round(4)
        summary['rss'] = summary['rss'].round(4)
        summary['pss'] = summary['pss'].round(4)

        logger.info(f"Computed {len(summary)} summary rows")

        # Delete existing data for this time range, then bulk insert
        with engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM load_summary WHERE snapshot_datetime >= :start"
            ), {'start': start})

        summary[['snapshot_datetime', 'host', 'username', 'comm', 'cpu_norm', 'rss', 'pss']].to_sql(
            'load_summary', engine, if_exists='append', index=False,
            method='multi', chunksize=500
        )

        logger.info(f"Wrote {len(summary)} rows to load_summary")

    except Exception as e:
        logger.error(f"data sync failed: {str(e)}")
        raise


if __name__ == "__main__":
    process_data()
