import time, pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from app.config import DB_CONFIG

engine = create_engine('mysql+pymysql://%s:%s@%s:%s/%s' % (DB_CONFIG['user'],DB_CONFIG['password'],DB_CONFIG['host'],DB_CONFIG['port'],DB_CONFIG['database']))

# Backfill from day 365 back to day 15 (we already have 14 days)
for day_offset in range(365, 14, -1):
    day_start = (datetime.now() - timedelta(days=day_offset)).strftime('%Y-%m-%d 00:00:00')
    day_end = (datetime.now() - timedelta(days=day_offset-1)).strftime('%Y-%m-%d 00:00:00')
    t0 = time.time()
    df = pd.read_sql(text("SELECT * FROM processes WHERE snapshot_datetime BETWEEN :s AND :e"), con=engine, params={'s': day_start, 'e': day_end})
    if df.empty:
        print('Day -%d: no data' % day_offset)
        continue
    df = df.sort_values(by='snapshot_datetime', ascending=True)
    df['rss'] = (df['rss'] / 1000000).round(4)
    df['cpu_diff'] = (df['cputimes'] - df.groupby(['host', 'pid'])['cputimes'].shift()).fillna(0)
    df['seconds_diff'] = (df['snapshot_time_epoch'] - df.groupby(['host', 'pid'])['snapshot_time_epoch'].shift()).fillna(0)
    df['cpu_norm'] = (df['cpu_diff'].div(df['seconds_diff'])).fillna(0).replace([float('inf'), float('-inf')], 0)
    df = df[(df['cpu_norm'] > 0) & (df['cpu_norm'] < 10000)]
    summary = df.groupby([pd.Grouper(key='snapshot_datetime', freq='5min'), 'host', 'username', 'comm']).agg(cpu_norm=('cpu_norm', 'sum'), rss=('rss', 'sum')).reset_index()
    summary = summary[(summary['cpu_norm'] > 0) | (summary['rss'] > 0)]
    summary['cpu_norm'] = summary['cpu_norm'].round(4)
    summary['rss'] = summary['rss'].round(4)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM load_summary WHERE snapshot_datetime BETWEEN :s AND :e"), {'s': day_start, 'e': day_end})
    summary[['snapshot_datetime', 'host', 'username', 'comm', 'cpu_norm', 'rss']].to_sql('load_summary', engine, if_exists='append', index=False, method='multi', chunksize=500)
    elapsed = time.time() - t0
    print('Day -%d: %d raw -> %d summary rows (%.1fs)' % (day_offset, len(df), len(summary), elapsed))
