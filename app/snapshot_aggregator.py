from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from app.config import DB_CONFIG

class SnapshotAggregator:
    def __init__(self):
        self.db_connection = create_engine(url="mysql+pymysql://{0}:{1}@{2}:{3}/{4}".format(
            DB_CONFIG['user'],
            DB_CONFIG['password'],
            DB_CONFIG['host'],
            DB_CONFIG['port'],
            DB_CONFIG['database']
        ))

    def aggregate_snapshots(self, start_date=None, end_date=None):
        """Aggregate process data into 5-minute snapshots"""
        if not start_date:
            start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        # First, create a CTE to calculate cpu_norm
        aggregation_query = """
        WITH cpu_calculations AS (
            SELECT 
                p1.*,
                (p1.cputimes - COALESCE(p2.cputimes, p1.cputimes)) as cpu_diff,
                (p1.snapshot_time_epoch - COALESCE(p2.snapshot_time_epoch, p1.snapshot_time_epoch)) as time_diff,
                (p1.cputimes - COALESCE(p2.cputimes, p1.cputimes)) / 
                    NULLIF((p1.snapshot_time_epoch - COALESCE(p2.snapshot_time_epoch, p1.snapshot_time_epoch)), 0) as cpu_norm
            FROM processes p1
            LEFT JOIN processes p2 ON p1.host = p2.host 
                AND p1.pid = p2.pid
                AND p2.snapshot_time_epoch = (
                    SELECT MAX(snapshot_time_epoch)
                    FROM processes p3
                    WHERE p3.host = p1.host 
                        AND p3.pid = p1.pid
                        AND p3.snapshot_time_epoch < p1.snapshot_time_epoch
                )
            WHERE p1.snapshot_datetime BETWEEN :start_date AND :end_date
        )
        INSERT INTO process_snapshots 
            (snapshot_datetime, host, username, comm, total_cpu_norm, total_rss, total_vsz, process_count)
        SELECT 
            DATE_FORMAT(snapshot_datetime, '%Y-%m-%d %H:%i:00') as snapshot_datetime,
            host,
            username,
            comm,
            AVG(CASE WHEN cpu_norm IS NULL OR cpu_norm < 0 THEN 0 ELSE cpu_norm END) as total_cpu_norm,
            SUM(rss) / 1000000 as total_rss,
            SUM(vsz) / 1000000 as total_vsz,
            COUNT(*) as process_count
        FROM cpu_calculations 
        GROUP BY 
            DATE_FORMAT(snapshot_datetime, '%Y-%m-%d %H:%i:00'),
            host,
            username,
            comm
        ON DUPLICATE KEY UPDATE
            total_cpu_norm = VALUES(total_cpu_norm),
            total_rss = VALUES(total_rss),
            total_vsz = VALUES(total_vsz),
            process_count = VALUES(process_count)
        """

        with self.db_connection.connect() as conn:
            conn.execute(
                text(aggregation_query),
                {"start_date": f"{start_date} 00:00:00", "end_date": f"{end_date} 23:59:59"}
            )
            conn.commit() 