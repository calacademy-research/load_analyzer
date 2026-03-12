#!/usr/bin/env python3
"""FastAPI backend for load analyzer dashboard (React frontend)."""

import datetime
from collections import OrderedDict
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from zoneinfo import ZoneInfo

from redis_transformer import RedisReader

app = FastAPI()
redis_reader = RedisReader()

SERVERS = [
    ('flor', 256, 1500),
    ('rosalindf', 256, 2000),
    ('alice', 192, 1000),
    ('tdobz', 96, 1000),
    ('ibss-spark-1', 20, 121),
]
GPU_HOSTS = ['alice', 'ibss-spark-1']

# Plotly qualitative color palettes (matching dash_graph.py USER_COLORS)
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
        start_dt = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) - datetime.timedelta(days=1)
    if end:
        end_dt = datetime.datetime.strptime(end, '%Y-%m-%d')
    else:
        end_dt = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) + datetime.timedelta(days=1)
    end_dt += datetime.timedelta(days=1)
    return (
        start_dt.replace(tzinfo=datetime.timezone.utc),
        end_dt.replace(tzinfo=datetime.timezone.utc),
    )


def _convert_to_df(data_dict: OrderedDict, data_type: str, data_key: str) -> pd.DataFrame:
    """Convert Redis data dict to DataFrame. Mirrors DashGraph._convert_to_df."""
    df_dict = {}
    for key, value in data_dict.items():
        entry_data = value.get(data_type, {}).get(data_key, {})
        if not entry_data:
            continue
        if isinstance(entry_data, dict):
            entry_data = [entry_data]
        for entry in entry_data:
            if entry:
                df_dict.setdefault('snapshot_datetime', []).append(
                    datetime.datetime.fromtimestamp(key)
                )
                for ek, ev in entry.items():
                    df_dict.setdefault(ek, []).append(ev)
    return pd.DataFrame(df_dict)


def _build_hover_text(command_df: pd.DataFrame, graph_data: OrderedDict,
                      data_type: str, value_field: str) -> list:
    """Build per-timestamp hover text from user-level data."""
    users_df = _convert_to_df(graph_data, data_type, 'user')
    if users_df.empty:
        return []

    users_df = users_df.sort_values(['snapshot_datetime', value_field], ascending=[True, False])
    grouped = dict(list(users_df.groupby('snapshot_datetime')))

    label = 'mem' if data_type == 'mem' else 'load'
    unit = 'G' if data_type == 'mem' else ''

    result = []
    for ts in command_df['snapshot_datetime']:
        chunk = grouped.get(ts, pd.DataFrame())
        parts = []
        for _, row in chunk.iterrows():
            parts.append(
                f"Host: {row['host']}  user: {row['username']}  "
                f"{label}: {row[value_field]:.2f}{unit}  cmd: {row['comm']}"
            )
        result.append(parts)
    return result


@app.get("/api/config")
async def get_config():
    return {
        "servers": [
            {"hostname": h, "cpu_limit": c, "mem_limit": m, "has_gpu": h in GPU_HOSTS}
            for h, c, m in SERVERS
        ],
        "refresh_interval_ms": 120000,
        "user_colors": USER_COLORS,
    }


@app.get("/api/overview")
async def get_overview(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_dt, end_dt = _parse_dates(start, end)
    result = []

    for hostname, cpu_limit, mem_limit in SERVERS:
        graph_data = redis_reader.get_data(hostname, start_dt, end_dt)
        server_entry = {
            "hostname": hostname,
            "cpu_limit": cpu_limit,
            "mem_limit": mem_limit,
            "has_gpu": hostname in GPU_HOSTS,
            "cpu": None,
            "mem": None,
            "gpu": None,
        }

        # CPU data
        cpu_df = _convert_to_df(graph_data, 'cpu', 'command')
        if not cpu_df.empty:
            hover = _build_hover_text(cpu_df, graph_data, 'cpu', 'cpu_norm')
            server_entry["cpu"] = {
                "timestamps": cpu_df['snapshot_datetime'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
                "values": cpu_df['cpu_norm'].round(2).tolist(),
                "hover": hover,
            }

        # Memory data
        mem_df = _convert_to_df(graph_data, 'mem', 'command')
        if not mem_df.empty:
            hover = _build_hover_text(mem_df, graph_data, 'mem', 'rss')
            server_entry["mem"] = {
                "timestamps": mem_df['snapshot_datetime'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
                "values": mem_df['rss'].clip(upper=mem_limit).round(2).tolist(),
                "raw_values": mem_df['rss'].round(2).tolist(),
                "hover": hover,
            }

        # GPU data
        if hostname in GPU_HOSTS:
            gpu_data = redis_reader.get_gpu_data(hostname, start_dt, end_dt)
            if gpu_data:
                rows = []
                for ts, data in gpu_data.items():
                    rows.append({
                        'snapshot_datetime': datetime.datetime.fromtimestamp(ts),
                        'utilization_pct': data.get('utilization_pct', 0),
                        'memory_used_mb': data.get('memory_used_mb', 0),
                        'memory_total_mb': data.get('memory_total_mb', 0),
                        'gpu_count': data.get('gpu_count', 0),
                        'gpu_processes': data.get('gpu_processes', ''),
                    })
                gpu_df = pd.DataFrame(rows)
                server_entry["gpu"] = {
                    "timestamps": gpu_df['snapshot_datetime'].dt.strftime('%Y-%m-%dT%H:%M:%S').tolist(),
                    "utilization_pct": gpu_df['utilization_pct'].round(1).tolist(),
                    "memory_used_mb": gpu_df['memory_used_mb'].round(0).tolist(),
                    "memory_total_mb": gpu_df['memory_total_mb'].round(0).tolist(),
                    "gpu_count": gpu_df['gpu_count'].tolist(),
                    "gpu_processes": gpu_df['gpu_processes'].fillna('').tolist(),
                }

        result.append(server_entry)

    return {"servers": result}


@app.get("/api/per-user")
async def get_per_user(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_dt, end_dt = _parse_dates(start, end)
    servers_result = []
    top_consumers = []

    for hostname, cpu_limit, mem_limit in SERVERS:
        graph_data = redis_reader.get_data(hostname, start_dt, end_dt)
        if not graph_data:
            continue

        server_entry = {
            "hostname": hostname,
            "cpu_limit": cpu_limit,
            "mem_limit": mem_limit,
            "cpu_by_user": None,
            "mem_by_user": None,
        }

        cpu_user_df = _convert_to_df(graph_data, 'cpu', 'user')
        mem_user_df = _convert_to_df(graph_data, 'mem', 'user')

        # CPU by user
        if not cpu_user_df.empty:
            by_user = cpu_user_df.groupby(['snapshot_datetime', 'username'])['cpu_norm'].sum().reset_index()
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
            agg = cpu_user_df.groupby('username').agg(
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
        if not mem_user_df.empty:
            by_user = mem_user_df.groupby(['snapshot_datetime', 'username'])['rss'].sum().reset_index()
            user_totals = by_user.groupby('username')['rss'].sum().sort_values(ascending=False)
            top_users = list(user_totals.index[:10])
            if len(user_totals) > 10:
                by_user.loc[~by_user['username'].isin(top_users), 'username'] = 'other'
                by_user = by_user.groupby(['snapshot_datetime', 'username'])['rss'].sum().reset_index()
                top_users.append('other')

            all_ts = sorted(by_user['snapshot_datetime'].unique())
            series = {}
            for user in top_users:
                ud = by_user[by_user['username'] == user].set_index('snapshot_datetime')
                series[user] = [round(float(ud.loc[t, 'rss']), 2) if t in ud.index else 0 for t in all_ts]

            server_entry["mem_by_user"] = {
                "timestamps": [t.strftime('%Y-%m-%dT%H:%M:%S') for t in all_ts],
                "users": top_users,
                "series": series,
            }

            # Top consumers: Memory — merge with existing CPU entries
            agg = mem_user_df.groupby('username').agg(
                avg_mem=('rss', 'mean'),
                peak_mem=('rss', 'max'),
            ).reset_index()
            for _, row in agg.iterrows():
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

    # Sort top consumers by peak CPU descending
    top_consumers.sort(key=lambda x: x.get('peak_cpu') or 0, reverse=True)

    return {"servers": servers_result, "top_consumers": top_consumers}


# Serve React frontend (must be mounted AFTER API routes)
import os
frontend_dist = os.path.join(os.path.dirname(__file__), 'frontend', 'dist')
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
