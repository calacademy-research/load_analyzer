#!/usr/bin/env python3
"""FastAPI backend for load analyzer dashboard (React frontend).
Reads pre-aggregated data from MySQL load_summary table (populated by process_data_job.py)
and GPU data from gpu_stats table.
"""

import datetime
import json
import numpy as np
import os
import time
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from zoneinfo import ZoneInfo

from app.config import DB_CONFIG

app = FastAPI()

# Simple in-memory TTL cache — stores pre-serialized JSON bytes
# Data updates every 5 min, so 2 min TTL is safe
_cache = {}
CACHE_TTL = 120  # seconds


def _cache_key(endpoint: str, start: str, end: str) -> str:
    return f"{endpoint}:{start}:{end}"


def _cache_get_json(key: str) -> Optional[bytes]:
    """Return cached JSON bytes, or None if miss/expired."""
    entry = _cache.get(key)
    if entry and time.time() - entry['time'] < CACHE_TTL:
        return entry['json']
    return None


def _cache_set_json(key: str, data: dict) -> bytes:
    """Serialize data to JSON bytes, cache it, and return the bytes."""
    json_bytes = json.dumps(data, default=str).encode()
    now = time.time()
    if len(_cache) > 50:
        expired = [k for k, v in _cache.items() if now - v['time'] > CACHE_TTL]
        for k in expired:
            del _cache[k]
    _cache[key] = {'json': json_bytes, 'time': now}
    return json_bytes


def _json_response(json_bytes: bytes) -> Response:
    return Response(content=json_bytes, media_type="application/json")

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
            f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
            pool_recycle=3600,
        )
    return _engine


SERVERS = [
    # Public
    ('flor', 256, 1500),
    ('rosalindf', 256, 2000),
    ('alice', 192, 1000),
    ('tdobz', 96, 1000),
    ('ibss-spark-1', 20, 121),
    # Private
    ('dirac', 576, 755),
    ('blackburn', 256, 1500),
    ('rudra', 256, 500),
    ('kali', 128, 500),
    ('deepsquid', 64, 250),
    ('deepsheep', 32, 188),
]
GPU_HOSTS = ['alice', 'ibss-spark-1', 'deepsquid', 'deepsheep']

USER_COLORS = [
    '#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A',
    '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52',
    '#66C2A5', '#FC8D62', '#8DA0CB', '#E78AC3', '#A6D854',
    '#FFD92F', '#E5C494', '#B3B3B3',
    '#B3E2CD', '#FDCDAC', '#CBD5E8', '#F4CAE4', '#E6F5C9',
    '#FFF2AE', '#F1E2CC', '#CCCCCC',
]


def _parse_dates(start: Optional[str], end: Optional[str]):
    if start:
        start_dt = datetime.datetime.strptime(start, '%Y-%m-%d')
    else:
        start_dt = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) - datetime.timedelta(days=14)
    if end:
        end_dt = datetime.datetime.strptime(end, '%Y-%m-%d')
    else:
        end_dt = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) + datetime.timedelta(days=1)
    end_dt += datetime.timedelta(days=1)
    # Round start to day boundary for stable cache keys
    start_str = start_dt.strftime('%Y-%m-%d') + ' 00:00:00'
    end_str = end_dt.strftime('%Y-%m-%d') + ' 00:00:00'
    return start_str, end_str


def _query_df(sql: str, params: dict) -> pd.DataFrame:
    engine = get_engine()
    df = pd.read_sql(text(sql), con=engine, params=params)
    # Replace inf/NaN with 0 to avoid JSON serialization errors
    df = df.replace([np.inf, -np.inf], 0).fillna(0)
    return df


@app.get("/api/config")
async def get_config():
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT MIN(snapshot_datetime) FROM load_summary")).fetchone()
        data_start = row[0].strftime('%Y-%m-%d') if row and row[0] else None
    return {
        "servers": [
            {"hostname": h, "cpu_limit": c, "mem_limit": m, "has_gpu": h in GPU_HOSTS}
            for h, c, m in SERVERS
        ],
        "refresh_interval_ms": 120000,
        "user_colors": USER_COLORS,
        "data_start": data_start,
    }


def _cap_mem_at_host_limits(df):
    """Cap total memory per snapshot per host at the host's physical memory limit.

    RSS over-counts shared mmap'd memory (e.g. BLAST's nt database appears as
    full RSS in every process). When total reported memory exceeds what the host
    physically has, scale all user values down proportionally.
    """
    if df.empty:
        return
    mem_limits = df['host'].map({h: m for h, _, m in SERVERS})
    group_total = df.groupby(['snapshot_datetime', 'host'])['mem'].transform('sum')
    scale = (mem_limits / group_total).clip(upper=1.0)
    df['mem'] = df['mem'] * scale


def _resample_bucket(start_str: str, end_str: str) -> str:
    """Choose resample frequency based on date range size."""
    s = datetime.datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
    e = datetime.datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
    days = (e - s).total_seconds() / 86400
    if days > 7:
        return '30min'
    elif days > 3:
        return '15min'
    return '5min'


def _build_hover(grouped_df, hostname, sort_col, fmt_fn):
    """Build hover text lists efficiently using pre-sorted groups."""
    hover_dict = {}
    # Sort entire df once, then iterate groups
    sorted_df = grouped_df.sort_values(sort_col, ascending=False)
    for ts, group in sorted_df.groupby('snapshot_datetime'):
        parts = []
        for _, row in group.head(15).iterrows():
            parts.append(fmt_fn(hostname, row))
        hover_dict[ts] = parts
    return hover_dict


@app.get("/api/overview")
async def get_overview(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_str, end_str = _parse_dates(start, end)
    ck = _cache_key('overview', start_str, end_str)
    cached = _cache_get_json(ck)
    if cached:
        return _json_response(cached)

    bucket = _resample_bucket(start_str, end_str)
    result = []

    # Get all load_summary data for the date range in one query
    df = _query_df(
        "SELECT snapshot_datetime, host, username, comm, cpu_norm, rss, pss "
        "FROM load_summary WHERE snapshot_datetime BETWEEN :start AND :end",
        {'start': start_str, 'end': end_str}
    )

    # Use PSS where available, fall back to RSS
    if not df.empty:
        df['mem'] = df['pss'].where(df['pss'] > 0, df['rss'])
    else:
        df['mem'] = 0.0

    _cap_mem_at_host_limits(df)

    # Resample to larger buckets if needed
    if bucket != '5min' and not df.empty:
        df['snapshot_datetime'] = df['snapshot_datetime'].dt.floor(bucket)
        df = df.groupby(['snapshot_datetime', 'host', 'username', 'comm']).agg(
            cpu_norm=('cpu_norm', 'sum'),
            mem=('mem', 'mean'),  # average memory across sub-buckets
        ).reset_index()

    # Get all GPU data for the date range (aggregate across gpu_index per timestamp)
    gpu_df = _query_df(
        "SELECT snapshot_datetime, host, "
        "AVG(utilization_pct) AS utilization_pct, "
        "SUM(memory_used_mb) AS memory_used_mb, "
        "SUM(memory_total_mb) AS memory_total_mb, "
        "COUNT(DISTINCT gpu_index) AS gpu_count, "
        "GROUP_CONCAT(gpu_processes SEPARATOR ', ') AS gpu_processes "
        "FROM gpu_stats WHERE snapshot_datetime BETWEEN :start AND :end "
        "GROUP BY snapshot_datetime, host",
        {'start': start_str, 'end': end_str}
    )

    # Resample GPU data too
    if bucket != '5min' and not gpu_df.empty:
        gpu_df['snapshot_datetime'] = gpu_df['snapshot_datetime'].dt.floor(bucket)
        gpu_df = gpu_df.groupby(['snapshot_datetime', 'host']).agg(
            utilization_pct=('utilization_pct', 'mean'),
            memory_used_mb=('memory_used_mb', 'mean'),
            memory_total_mb=('memory_total_mb', 'max'),
            gpu_count=('gpu_count', 'max'),
            gpu_processes=('gpu_processes', 'first'),
        ).reset_index()

    for hostname, cpu_limit, mem_limit in SERVERS:
        server_entry = {
            "hostname": hostname,
            "cpu_limit": cpu_limit,
            "mem_limit": mem_limit,
            "has_gpu": hostname in GPU_HOSTS,
            "cpu": None,
            "mem": None,
            "gpu": None,
        }

        host_df = df[df['host'] == hostname] if not df.empty else pd.DataFrame()

        if not host_df.empty:
            # Pre-aggregate per-user-per-timestamp once for hover text
            user_by_time = host_df.groupby(['snapshot_datetime', 'username', 'comm']).agg(
                cpu_norm=('cpu_norm', 'sum'), mem=('mem', 'sum')
            ).reset_index()

            # CPU aggregation
            cpu_by_time = host_df.groupby('snapshot_datetime')['cpu_norm'].sum().reset_index()
            cpu_by_time = cpu_by_time.sort_values('snapshot_datetime')

            cpu_hover = _build_hover(
                user_by_time, hostname, 'cpu_norm',
                lambda h, r: f"Host: {h}  user: {r['username']}  load: {r['cpu_norm']:.2f}  cmd: {r['comm']}"
            )

            server_entry["cpu"] = {
                "timestamps": cpu_by_time['snapshot_datetime'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
                "values": cpu_by_time['cpu_norm'].round(2).tolist(),
                "hover": [cpu_hover.get(ts, []) for ts in cpu_by_time['snapshot_datetime']],
            }

            # Memory aggregation
            mem_by_time = host_df.groupby('snapshot_datetime')['mem'].sum().reset_index()
            mem_by_time = mem_by_time.sort_values('snapshot_datetime')

            mem_hover = _build_hover(
                user_by_time, hostname, 'mem',
                lambda h, r: f"Host: {h}  user: {r['username']}  mem: {r['mem']:.2f}G  cmd: {r['comm']}"
            )

            server_entry["mem"] = {
                "timestamps": mem_by_time['snapshot_datetime'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
                "values": mem_by_time['mem'].clip(upper=mem_limit).round(2).tolist(),
                "raw_values": mem_by_time['mem'].round(2).tolist(),
                "hover": [mem_hover.get(ts, []) for ts in mem_by_time['snapshot_datetime']],
            }

        # GPU data
        if hostname in GPU_HOSTS and not gpu_df.empty:
            host_gpu = gpu_df[gpu_df['host'] == hostname].sort_values('snapshot_datetime')
            if not host_gpu.empty:
                server_entry["gpu"] = {
                    "timestamps": host_gpu['snapshot_datetime'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
                    "utilization_pct": host_gpu['utilization_pct'].round(1).tolist(),
                    "memory_used_mb": host_gpu['memory_used_mb'].round(0).tolist(),
                    "memory_total_mb": host_gpu['memory_total_mb'].round(0).tolist(),
                    "gpu_count": host_gpu['gpu_count'].tolist(),
                    "gpu_processes": host_gpu['gpu_processes'].fillna('').tolist(),
                }

        result.append(server_entry)

    response = {"servers": result}
    return _json_response(_cache_set_json(ck, response))


@app.get("/api/per-user")
async def get_per_user(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_str, end_str = _parse_dates(start, end)
    ck = _cache_key('per-user', start_str, end_str)
    cached = _cache_get_json(ck)
    if cached:
        return _json_response(cached)

    bucket = _resample_bucket(start_str, end_str)

    df = _query_df(
        "SELECT snapshot_datetime, host, username, comm, cpu_norm, rss, pss "
        "FROM load_summary WHERE snapshot_datetime BETWEEN :start AND :end",
        {'start': start_str, 'end': end_str}
    )

    # Use PSS where available, fall back to RSS
    if not df.empty:
        df['mem'] = df['pss'].where(df['pss'] > 0, df['rss'])
    else:
        df['mem'] = 0.0

    _cap_mem_at_host_limits(df)

    # Resample to larger buckets if needed
    if bucket != '5min' and not df.empty:
        df['snapshot_datetime'] = df['snapshot_datetime'].dt.floor(bucket)
        df = df.groupby(['snapshot_datetime', 'host', 'username', 'comm']).agg(
            cpu_norm=('cpu_norm', 'sum'),
            mem=('mem', 'mean'),
        ).reset_index()

    servers_result = []
    top_consumers = []

    for hostname, cpu_limit, mem_limit in SERVERS:
        host_df = df[df['host'] == hostname] if not df.empty else pd.DataFrame()
        if host_df.empty:
            continue

        server_entry = {
            "hostname": hostname,
            "cpu_limit": cpu_limit,
            "mem_limit": mem_limit,
            "cpu_by_user": None,
            "mem_by_user": None,
        }

        # CPU by user
        by_user = host_df.groupby(['snapshot_datetime', 'username'])['cpu_norm'].sum().reset_index()
        user_totals = by_user.groupby('username')['cpu_norm'].sum().sort_values(ascending=False)
        top_users = list(user_totals.index[:10])
        if len(user_totals) > 10:
            by_user.loc[~by_user['username'].isin(top_users), 'username'] = 'other'
            by_user = by_user.groupby(['snapshot_datetime', 'username'])['cpu_norm'].sum().reset_index()
            top_users.append('other')

        all_ts = sorted(by_user['snapshot_datetime'].unique())
        series = {}
        for user in top_users:
            ud = by_user[by_user['username'] == user].set_index('snapshot_datetime')
            series[user] = [round(float(ud.loc[t, 'cpu_norm']), 2) if t in ud.index else 0 for t in all_ts]

        server_entry["cpu_by_user"] = {
            "timestamps": [t.strftime('%Y-%m-%dT%H:%M:%S') for t in all_ts],
            "users": top_users,
            "series": series,
        }

        # Top consumers: CPU
        agg = host_df.groupby('username').agg(
            avg_cpu=('cpu_norm', 'mean'),
            peak_cpu=('cpu_norm', 'max'),
        ).reset_index()
        for _, row in agg.iterrows():
            top_consumers.append({
                "server": hostname,
                "user": row['username'],
                "avg_cpu": round(float(row['avg_cpu']), 1),
                "peak_cpu": round(float(row['peak_cpu']), 1),
                "avg_mem": None,
                "peak_mem": None,
            })

        # Memory by user
        by_user_mem = host_df.groupby(['snapshot_datetime', 'username'])['mem'].sum().reset_index()
        user_totals_mem = by_user_mem.groupby('username')['mem'].sum().sort_values(ascending=False)
        top_users_mem = list(user_totals_mem.index[:10])
        if len(user_totals_mem) > 10:
            by_user_mem.loc[~by_user_mem['username'].isin(top_users_mem), 'username'] = 'other'
            by_user_mem = by_user_mem.groupby(['snapshot_datetime', 'username'])['mem'].sum().reset_index()
            top_users_mem.append('other')

        all_ts_mem = sorted(by_user_mem['snapshot_datetime'].unique())
        series_mem = {}
        for user in top_users_mem:
            ud = by_user_mem[by_user_mem['username'] == user].set_index('snapshot_datetime')
            series_mem[user] = [round(float(ud.loc[t, 'mem']), 2) if t in ud.index else 0 for t in all_ts_mem]

        server_entry["mem_by_user"] = {
            "timestamps": [t.strftime('%Y-%m-%dT%H:%M:%S') for t in all_ts_mem],
            "users": top_users_mem,
            "series": series_mem,
        }

        # Top consumers: Memory — merge with existing CPU entries
        agg_mem = host_df.groupby('username').agg(
            avg_mem=('mem', 'mean'),
            peak_mem=('mem', 'max'),
        ).reset_index()
        for _, row in agg_mem.iterrows():
            existing = [c for c in top_consumers
                        if c['server'] == hostname and c['user'] == row['username']]
            if existing:
                existing[0]['avg_mem'] = round(float(row['avg_mem']), 1)
                existing[0]['peak_mem'] = round(float(row['peak_mem']), 1)
            else:
                top_consumers.append({
                    "server": hostname,
                    "user": row['username'],
                    "avg_cpu": None,
                    "peak_cpu": None,
                    "avg_mem": round(float(row['avg_mem']), 1),
                    "peak_mem": round(float(row['peak_mem']), 1),
                })

        servers_result.append(server_entry)

    top_consumers.sort(key=lambda x: x.get('peak_cpu') or 0, reverse=True)
    response = {"servers": servers_result, "top_consumers": top_consumers}
    return _json_response(_cache_set_json(ck, response))


@app.get("/api/analytics")
async def get_analytics(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    """Compute core-hours, GB-hours, server utilization, and top programs."""
    start_str, end_str = _parse_dates(start, end)
    ck = _cache_key('analytics', start_str, end_str)
    cached = _cache_get_json(ck)
    if cached:
        return _json_response(cached)

    BUCKET_HOURS = 5 / 60  # each row represents a 5-minute bucket

    df = _query_df(
        "SELECT snapshot_datetime, host, username, comm, cpu_norm, rss, pss "
        "FROM load_summary WHERE snapshot_datetime BETWEEN :start AND :end",
        {'start': start_str, 'end': end_str}
    )

    # Use PSS where available, fall back to RSS
    if not df.empty:
        df['mem'] = df['pss'].where(df['pss'] > 0, df['rss'])
    else:
        df['mem'] = 0.0

    _cap_mem_at_host_limits(df)

    server_totals = []
    for hostname, cpu_limit, mem_limit in SERVERS:
        host_df = df[df['host'] == hostname] if not df.empty else pd.DataFrame()

        if host_df.empty:
            server_totals.append({
                "hostname": hostname, "cpu_limit": cpu_limit, "mem_limit": mem_limit,
                "avg_cpu_pct": 0, "peak_cpu_pct": 0, "avg_mem_pct": 0, "peak_mem_pct": 0,
                "total_core_hours": 0,
            })
            continue

        # Aggregate per timestamp for server-level stats
        by_time = host_df.groupby('snapshot_datetime').agg(
            cpu_total=('cpu_norm', 'sum'), mem_total=('mem', 'sum')
        ).reset_index()

        avg_cpu = float(by_time['cpu_total'].mean())
        peak_cpu = float(by_time['cpu_total'].max())
        avg_mem = float(by_time['mem_total'].mean())
        peak_mem = float(by_time['mem_total'].max())

        server_totals.append({
            "hostname": hostname,
            "cpu_limit": cpu_limit,
            "mem_limit": mem_limit,
            "avg_cpu_pct": round(avg_cpu / cpu_limit * 100, 1),
            "peak_cpu_pct": round(peak_cpu / cpu_limit * 100, 1),
            "avg_mem_pct": round(avg_mem / mem_limit * 100, 1),
            "peak_mem_pct": round(peak_mem / mem_limit * 100, 1),
            "total_core_hours": round(float(by_time['cpu_total'].sum()) * BUCKET_HOURS, 1),
        })

    # Top users by core-hours
    users_by_cpu = []
    if not df.empty:
        by_user = df.groupby('username')['cpu_norm'].sum() * BUCKET_HOURS
        by_user = by_user.sort_values(ascending=False).head(20)
        by_user_server = df.groupby(['username', 'host'])['cpu_norm'].sum() * BUCKET_HOURS
        for user in by_user.index:
            servers = {}
            for (u, h), val in by_user_server.items():
                if u == user:
                    servers[h] = round(float(val), 1)
            users_by_cpu.append({
                "user": user,
                "core_hours": round(float(by_user[user]), 1),
                "servers": servers,
            })

    # Top users by GB-hours
    users_by_mem = []
    if not df.empty:
        by_user = df.groupby('username')['mem'].sum() * BUCKET_HOURS
        by_user = by_user.sort_values(ascending=False).head(20)
        by_user_server = df.groupby(['username', 'host'])['mem'].sum() * BUCKET_HOURS
        for user in by_user.index:
            servers = {}
            for (u, h), val in by_user_server.items():
                if u == user:
                    servers[h] = round(float(val), 1)
            users_by_mem.append({
                "user": user,
                "gb_hours": round(float(by_user[user]), 1),
                "servers": servers,
            })

    # Top programs by core-hours
    top_programs = []
    if not df.empty:
        by_prog = df.groupby('comm').agg(
            core_hours=('cpu_norm', 'sum'),
            gb_hours=('mem', 'sum'),
        ).reset_index()
        by_prog['core_hours'] = (by_prog['core_hours'] * BUCKET_HOURS).round(1)
        by_prog['gb_hours'] = (by_prog['gb_hours'] * BUCKET_HOURS).round(1)
        by_prog = by_prog.sort_values('core_hours', ascending=False).head(10)

        prog_users = df.groupby('comm')['username'].apply(lambda x: sorted(set(x)))

        for _, row in by_prog.iterrows():
            prog = row['comm']
            top_programs.append({
                "program": prog,
                "core_hours": float(row['core_hours']),
                "gb_hours": float(row['gb_hours']),
                "users": prog_users.get(prog, []),
            })

    server_totals.sort(key=lambda x: x['total_core_hours'], reverse=True)

    response = {
        "users_by_cpu": users_by_cpu,
        "users_by_mem": users_by_mem,
        "server_utilization": server_totals,
        "top_programs": top_programs,
    }
    return _json_response(_cache_set_json(ck, response))


@app.get("/api/slurm-efficiency")
async def get_slurm_efficiency(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    """Return Slurm allocation efficiency data for the given date range."""
    start_str, end_str = _parse_dates(start, end)

    ck = _cache_key('slurm-efficiency', start_str, end_str)
    cached = _cache_get_json(ck)
    if cached:
        return _json_response(cached)

    # Aggregate per user in SQL (one row per user) rather than pulling every job row into
    # pandas - the ~100k-row transfer was the slow part. Efficiency is size-weighted
    # (sum used / sum requested) so it equals Avg Used / Avg Requested.
    df = _query_df(
        "SELECT username, COUNT(*) AS job_count, "
        "SUM(max_rss_gb > 0 AND req_mem_gb > 0) AS mem_measured, "
        "SUM(CASE WHEN max_rss_gb > 0 AND req_mem_gb > 0 THEN req_mem_gb ELSE 0 END) AS mem_req, "
        "SUM(CASE WHEN max_rss_gb > 0 AND req_mem_gb > 0 THEN max_rss_gb ELSE 0 END) AS mem_used, "
        "SUM(CASE WHEN max_rss_gb > 0 AND req_mem_gb > 0 "
        "    THEN GREATEST(0, req_mem_gb - max_rss_gb) * elapsed_seconds / 3600 ELSE 0 END) AS mem_wasted_gbh, "
        "SUM(total_cpu_seconds > 0 AND alloc_cpus > 0 AND elapsed_seconds > 0) AS cpu_measured, "
        "SUM(CASE WHEN total_cpu_seconds > 0 AND alloc_cpus > 0 AND elapsed_seconds > 0 "
        "    THEN alloc_cpus * elapsed_seconds ELSE 0 END) AS cpu_alloc_cs, "
        "SUM(CASE WHEN total_cpu_seconds > 0 AND alloc_cpus > 0 AND elapsed_seconds > 0 "
        "    THEN total_cpu_seconds ELSE 0 END) AS cpu_used_cs, "
        "SUM(CASE WHEN total_cpu_seconds > 0 AND alloc_cpus > 0 AND elapsed_seconds > 0 "
        "    THEN elapsed_seconds ELSE 0 END) AS cpu_elapsed "
        "FROM slurm_jobs WHERE start_time BETWEEN :start AND :end "
        "AND state IN ('COMPLETED', 'TIMEOUT', 'CANCELLED') GROUP BY username",
        {'start': start_str, 'end': end_str}
    )

    user_summary = []
    cpu_summary = []
    for _, r in df.iterrows():
        jc = int(r['job_count'])
        mm = int(r['mem_measured'])
        sum_req = float(r['mem_req'])
        if mm > 0 and sum_req > 0:
            sum_used = float(r['mem_used'])
            eff = round(sum_used / sum_req * 100, 1)
            user_summary.append({
                "username": r['username'],
                "job_count": jc,
                "measured_jobs": mm,
                "coverage_pct": round(mm / jc * 100, 1) if jc else 0,
                "avg_mem_efficiency": eff,
                "wasted_pct": round(100 - eff, 1),
                "total_wasted_gb_hours": round(float(r['mem_wasted_gbh']), 1),
                "avg_req_mem_gb": round(sum_req / mm, 1),
                "avg_max_rss_gb": round(sum_used / mm, 1),
            })
        cm = int(r['cpu_measured'])
        alloc_cs = float(r['cpu_alloc_cs'])
        cpu_elapsed = float(r['cpu_elapsed'])
        if cm > 0 and alloc_cs > 0 and cpu_elapsed > 0:
            used_cs = float(r['cpu_used_cs'])
            ceff = round(used_cs / alloc_cs * 100, 1)
            cpu_summary.append({
                "username": r['username'],
                "job_count": jc,
                "measured_jobs": cm,
                "coverage_pct": round(cm / jc * 100, 1) if jc else 0,
                "cpu_wasted_pct": round(100 - ceff, 1),
                "total_wasted_core_hours": round(max(0.0, alloc_cs - used_cs) / 3600, 1),
                "avg_alloc_cpus": round(alloc_cs / cpu_elapsed, 1),
                "avg_used_cpus": round(used_cs / cpu_elapsed, 2),
            })
    user_summary.sort(key=lambda x: x['wasted_pct'], reverse=True)
    cpu_summary.sort(key=lambda x: x['cpu_wasted_pct'], reverse=True)

    result = {"user_summary": user_summary, "cpu_summary": cpu_summary}
    return _json_response(_cache_set_json(ck, result))


@app.get("/api/users")
async def get_users():
    """Return distinct usernames from the processes table."""
    ck = _cache_key('users', 'all', 'all')
    cached = _cache_get_json(ck)
    if cached:
        return _json_response(cached)

    df = _query_df(
        "SELECT DISTINCT username FROM load_summary ORDER BY username",
        {}
    )
    usernames = df['username'].tolist() if not df.empty else []
    response = {"users": usernames}
    return _json_response(_cache_set_json(ck, response))


@app.get("/api/user-processes")
async def get_user_processes(
    user: str = Query("all"),
    host: str = Query("all"),
    window: str = Query("active"),
):
    """Return list of processes for a given user (or all users), with summary stats."""
    ck = _cache_key(f'user-processes:{user}:{host}', window, '')
    cached = _cache_get_json(ck)
    if cached:
        return _json_response(cached)

    now = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles'))

    if window == "active":
        cutoff = now - datetime.timedelta(minutes=10)
    elif window == "24h":
        cutoff = now - datetime.timedelta(hours=24)
    elif window == "7d":
        cutoff = now - datetime.timedelta(days=7)
    elif window == "30d":
        cutoff = now - datetime.timedelta(days=30)
    elif window == "90d":
        cutoff = now - datetime.timedelta(days=90)
    elif window == "all":
        cutoff = datetime.datetime(2020, 1, 1, tzinfo=ZoneInfo('America/Los_Angeles'))
    else:
        return {"processes": [], "error": f"Unknown window: {window}"}

    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
    params = {'cutoff': cutoff_str}

    user_filter = ""
    if user != "all":
        user_filter = " AND username = :user"
        params['user'] = user

    host_filter = ""
    if host != "all":
        host_filter = " AND host = :host"
        params['host'] = host

    sql = (
        "SELECT host, pid, username, comm, "
        "MAX(args) AS args, "
        "MAX(rss) AS peak_rss, "
        "MAX(pss) AS peak_pss, "
        "MAX(cputimes) AS max_cputimes, "
        "MAX(thcount) AS max_thcount, "
        "MIN(snapshot_datetime) AS first_seen, "
        "MAX(snapshot_datetime) AS last_seen, "
        "MAX(etimes) AS etimes, "
        "COUNT(*) AS snapshot_count "
        "FROM processes "
        f"WHERE snapshot_datetime >= :cutoff{user_filter}{host_filter} "
        "GROUP BY host, pid, username, comm "
        "ORDER BY GREATEST(MAX(rss), MAX(pss)) DESC "
        "LIMIT 500"
    )

    df = _query_df(sql, params)

    if df.empty:
        return _json_response(_cache_set_json(ck, {"processes": []}))

    processes = []
    for _, row in df.iterrows():
        processes.append({
            "host": row['host'],
            "pid": int(row['pid']),
            "username": row['username'],
            "comm": row['comm'],
            "args": row['args'] if row['args'] else row['comm'],
            "peak_mem_gb": round((float(row["peak_pss"]) if float(row["peak_pss"]) > 0 else float(row["peak_rss"])) / 1024 / 1024, 2),
            "cpu_seconds": int(row['max_cputimes']),
            "threads": int(row['max_thcount']),
            "first_seen": str(row['first_seen']),
            "last_seen": str(row['last_seen']),
            "runtime_hours": round(float(row['etimes']) / 3600, 1),
            "snapshot_count": int(row['snapshot_count']),
        })

    response = {"processes": processes}
    return _json_response(_cache_set_json(ck, response))


@app.get("/api/process-history")
async def get_process_history(
    host: str = Query(...),
    pid: int = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    """Return time-series data for a specific process (host, pid)."""
    if start:
        start_dt = datetime.datetime.strptime(start, '%Y-%m-%d')
    else:
        start_dt = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) - datetime.timedelta(days=7)
    if end:
        end_dt = datetime.datetime.strptime(end, '%Y-%m-%d') + datetime.timedelta(days=1)
    else:
        end_dt = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) + datetime.timedelta(days=1)

    start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

    ck = _cache_key(f'process-history:{host}:{pid}', start_str, end_str)
    cached = _cache_get_json(ck)
    if cached:
        return _json_response(cached)

    df = _query_df(
        "SELECT comm, cputimes, rss, pss, vsz, thcount, etimes, ppid, args, "
        "snapshot_time_epoch, snapshot_datetime "
        "FROM processes "
        "WHERE host = :host AND pid = :pid "
        "AND snapshot_datetime BETWEEN :start AND :end "
        "ORDER BY snapshot_datetime",
        {'host': host, 'pid': pid, 'start': start_str, 'end': end_str}
    )

    empty_response = {
        "timestamps": [], "cpu_cores": [], "mem_gb": [], "threads": [],
        "comm": "", "args": "", "ppid": 0, "peak_mem_gb": 0,
        "total_cpu_seconds": 0, "first_seen": "", "last_seen": "", "segments": 0,
    }

    if df.empty:
        return _json_response(_cache_set_json(ck, empty_response))

    df = df.sort_values('snapshot_datetime').reset_index(drop=True)

    # PID reuse detection: if cputimes decreases, it's a new process instance
    df['cpu_delta'] = df['cputimes'].diff()
    df['time_delta'] = df['snapshot_time_epoch'].diff()

    reuse_points = df.index[df['cpu_delta'] < 0].tolist()
    num_segments = len(reuse_points) + 1

    if reuse_points:
        # Keep only the most recent continuous segment
        last_reuse = reuse_points[-1]
        df = df.loc[last_reuse:].copy()
        df['cpu_delta'] = df['cputimes'].diff()
        df['time_delta'] = df['snapshot_time_epoch'].diff()

    # Compute CPU cores used (rate of CPU time consumption)
    df['cpu_cores'] = (df['cpu_delta'] / df['time_delta']).clip(lower=0, upper=300)
    df['cpu_cores'] = df['cpu_cores'].fillna(0)
    df['mem_kb'] = df['pss'].where(df['pss'] > 0, df['rss'])
    df['mem_gb'] = df['mem_kb'] / 1024 / 1024

    df = df.replace([np.inf, -np.inf], 0).fillna(0)

    last_row = df.iloc[-1]

    response = {
        "timestamps": df['snapshot_datetime'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
        "cpu_cores": df['cpu_cores'].round(3).tolist(),
        "mem_gb": df['mem_gb'].round(3).tolist(),
        "threads": df['thcount'].astype(int).tolist(),
        "comm": str(last_row['comm']),
        "args": str(last_row['args']),
        "ppid": int(last_row['ppid']),
        "peak_mem_gb": round(float(df['mem_gb'].max()), 2),
        "total_cpu_seconds": int(last_row['cputimes']),
        "first_seen": str(df.iloc[0]['snapshot_datetime']),
        "last_seen": str(last_row['snapshot_datetime']),
        "segments": num_segments,
    }
    return _json_response(_cache_set_json(ck, response))


@app.on_event("startup")
async def warm_cache():
    """Pre-populate cache for the default date range so first page load is fast."""
    try:
        await get_overview(start=None, end=None)
    except Exception:
        pass  # don't block startup if DB is temporarily unavailable


# Serve React frontend (must be mounted AFTER API routes)
class CachedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        ctype = response.headers.get("content-type", "")
        if ctype.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

frontend_dist = os.path.join(os.path.dirname(__file__), 'frontend', 'dist')
if os.path.isdir(frontend_dist):
    app.mount("/", CachedStaticFiles(directory=frontend_dist, html=True), name="frontend")
