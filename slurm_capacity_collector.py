#!/usr/bin/env python3
"""Live Slurm capacity + per-user quota usage -> MySQL snapshot for the dashboard 'Capacity' tab.

Run host-side by cron every minute (like slurm_collector.py); SSHes to the controller
as the restricted `loadmon` key. Writes one JSON snapshot row to `slurm_live_snapshot`.

Capacity = nodes in the general pool (`main` partition) that can currently ACCEPT jobs
(up, not drained/down) — so it grows when a contrib node is loaned in and shrinks when a
node is drained. "User's max" = GrpTRES quota on the main partition.
"""
import json
import re
import subprocess
import sys
from datetime import datetime

from sqlalchemy import create_engine, text

from app.config import DB_CONFIG

SLURM_HOST = 'ibss-genomics'
SLURM_USER = 'loadmon'
KEY = '/admin/monitor-keys/monitor_ed25519'
POOL = 'main'                                  # the general schedulable pool
ACCEPTING_BASE = {'IDLE', 'MIXED', 'ALLOCATED'}  # base states that can run jobs
BLOCKED_FLAGS = ('DRAIN', 'DOWN', 'NOT_RESPONDING', 'FAIL', 'POWERED_DOWN', 'POWERING')


def ssh(cmd):
    r = subprocess.run(
        ['ssh', '-i', KEY, '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes',
         f'{SLURM_USER}@{SLURM_HOST}', cmd],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"ssh '{cmd}' failed: {r.stderr.strip()}")
    return r.stdout


def tres_mem_gb(s):
    """Parse a TRES memory value ('948952M', '1.50T', '1000G', '4000K') to GB."""
    if not s:
        return 0.0
    m = re.match(r'([\d.]+)\s*([KMGTP]?)', s.strip())
    if not m:
        return 0.0
    v = float(m.group(1))
    return v * {'K': 1 / 1048576, 'M': 1 / 1024, '': 1 / 1024, 'G': 1, 'T': 1024, 'P': 1048576}[m.group(2)]


def can_accept(state):
    toks = state.upper().replace('+', ' ').split()
    if not toks or toks[0] not in ACCEPTING_BASE:
        return False
    return not any(f in toks[1:] for f in BLOCKED_FLAGS)


def collect():
    # ---- cluster capacity: main-pool nodes that can accept jobs (dynamic) ----
    cpu_total = cpu_used = mem_total_mb = mem_used_mb = nodes = 0
    node_rows = []
    snap_minute = datetime.now().replace(second=0, microsecond=0)
    for line in ssh('scontrol show node -o').splitlines():
        if not line.strip():
            continue

        def g(k, d='0'):
            m = re.search(rf'\b{k}=(\S+)', line)
            return m.group(1) if m else d
        # Per-node allocation snapshot -> slurm_node_alloc (ALL nodes, any
        # partition, drained included — a draining node still holds its jobs'
        # allocation, which is what the Overview charts need to show).
        node_rows.append({
            'snapshot_datetime': snap_minute,
            'host': g('NodeName', ''),
            'alloc_cpus': int(g('CPUAlloc')),
            'total_cpus': int(g('CPUTot')),
            'alloc_mem_gb': round(int(g('AllocMem')) / 1024, 1),
            'total_mem_gb': round(int(g('RealMemory')) / 1024, 1),
            'state': g('State', ''),
        })
        if POOL not in g('Partitions', '').split(','):
            continue
        if not can_accept(g('State', '')):
            continue
        nodes += 1
        cpu_total += int(g('CPUTot'))
        cpu_used += int(g('CPUAlloc'))
        mem_total_mb += int(g('RealMemory'))
        mem_used_mb += int(g('AllocMem'))
    cluster = {
        'cpu_total': cpu_total, 'cpu_used': cpu_used,
        'mem_total_gb': round(mem_total_mb / 1024, 1), 'mem_used_gb': round(mem_used_mb / 1024, 1),
        'nodes_accepting': nodes,
    }

    # ---- per-user CURRENT usage from running jobs ----
    use_cpu, use_mem = {}, {}
    for line in ssh('squeue -t RUNNING -h -O username:30,tres-alloc:200').splitlines():
        user = line[:30].strip()
        if not user:
            continue
        tres = line[30:]
        cm = re.search(r'cpu=(\d+)', tres)
        mm = re.search(r'mem=([\d.]+[KMGTP]?)', tres)
        use_cpu[user] = use_cpu.get(user, 0) + (int(cm.group(1)) if cm else 0)
        use_mem[user] = use_mem.get(user, 0.0) + (tres_mem_gb(mm.group(1)) if mm else 0.0)

    # ---- per-user quotas (GrpTRES on the main partition) ----
    q_cpu, q_mem = {}, {}
    for line in ssh('sacctmgr show assoc -P -n format=user,partition,grptres').splitlines():
        f = line.split('|')
        if len(f) < 3 or not f[0] or f[1] != POOL:
            continue
        cm = re.search(r'cpu=(\d+)', f[2])
        mm = re.search(r'mem=([\d.]+[KMGTP]?)', f[2])
        if cm:
            q_cpu[f[0]] = int(cm.group(1))
        if mm:
            q_mem[f[0]] = tres_mem_gb(mm.group(1))

    # ---- only users with running jobs, sorted by CPU usage ----
    users = []
    for u in sorted(use_cpu, key=lambda x: -use_cpu[x]):
        cq, mq = q_cpu.get(u, 0), q_mem.get(u, 0.0)
        users.append({
            'user': u,
            'cpu_used': use_cpu[u], 'cpu_max': cq,
            'cpu_pct': round(100 * use_cpu[u] / cq, 1) if cq else None,
            'mem_used_gb': round(use_mem[u], 1), 'mem_max_gb': round(mq, 1),
            'mem_pct': round(100 * use_mem[u] / mq, 1) if mq else None,
        })

    return {'cluster': cluster, 'users': users,
            'updated_at': datetime.now().isoformat(timespec='seconds')}, node_rows


def write(snapshot, node_rows):
    eng = create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
        f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS slurm_live_snapshot "
                       "(k VARCHAR(32) PRIMARY KEY, v MEDIUMTEXT, updated_at DATETIME)"))
        c.execute(text("REPLACE INTO slurm_live_snapshot (k, v, updated_at) "
                       "VALUES ('snapshot', :v, NOW())"), {'v': json.dumps(snapshot)})
        c.execute(text("CREATE TABLE IF NOT EXISTS slurm_node_alloc ("
                       "snapshot_datetime DATETIME NOT NULL, "
                       "host VARCHAR(64) NOT NULL, "
                       "alloc_cpus INT NOT NULL, "
                       "total_cpus INT NOT NULL, "
                       "alloc_mem_gb FLOAT NOT NULL, "
                       "total_mem_gb FLOAT NOT NULL, "
                       "state VARCHAR(64), "
                       "PRIMARY KEY (snapshot_datetime, host))"))
        if node_rows:
            c.execute(text("REPLACE INTO slurm_node_alloc "
                           "(snapshot_datetime, host, alloc_cpus, total_cpus, "
                           "alloc_mem_gb, total_mem_gb, state) "
                           "VALUES (:snapshot_datetime, :host, :alloc_cpus, :total_cpus, "
                           ":alloc_mem_gb, :total_mem_gb, :state)"), node_rows)


if __name__ == '__main__':
    snap, node_rows = collect()
    write(snap, node_rows)
    json.dump(snap, sys.stdout, indent=2)
    print()
