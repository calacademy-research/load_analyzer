#!/usr/bin/env python3
import redis
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import date, datetime, timedelta
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from collections import OrderedDict
import time
from functools import wraps
from sqlalchemy import create_engine
from app.config import DB_CONFIG
from zoneinfo import ZoneInfo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

hosts = ['flor', 'rosalindf', 'alice', 'tdobz']

def timer(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        duration = end_time - start_time
        logger.info(f"{func.__name__} took {duration:.2f} seconds to execute")
        return result
    return wrapper

class RedisBase:
    """Base class for Redis operations with common initialization"""
    def __init__(self, host='localhost', port=6379, db=0):
        """
        Initialize Redis connection
        :param host: Redis host
        :param port: Redis port
        :param db: Redis database number
        """
        self.redis_client = redis.Redis(
            host=host, 
            port=port, 
            db=db, 
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )

    @timer
    def read_sql(self, start_date=None, end_date=None):
        print(f"start_date: {start_date}")
        print(f"end_date: {end_date}")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        if end_date is None:
            end_date = (datetime.now()).strftime('%Y-%m-%d %H:%M:%S')

        db_connection = create_engine(url="mysql+pymysql://{0}:{1}@{2}:{3}/{4}".format(
            DB_CONFIG['user'],
            DB_CONFIG['password'],
            DB_CONFIG['host'],
            DB_CONFIG['port'],
            DB_CONFIG['database']
        ))
        print(f"connected to database on {DB_CONFIG['host']}...")
        sql_string = f"SELECT * FROM processes WHERE snapshot_datetime BETWEEN '{start_date}' AND '{end_date}'"
        print(f"Reading using sql: {sql_string}")

        df = pd.read_sql(sql_string, con=db_connection)
        print("db read complete.")
        return df


class RedisReader(RedisBase):
    """Class for reading data from Redis"""
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(redis.RedisError)
    )
    @timer
    def get_data(self, host: Optional[str] = None, 
                 start_time: Optional[datetime] = None, 
                 end_time: Optional[datetime] = None,
                 sort_by_time: bool = True) -> List[Dict]:
        """
        Get data by time range
        :param data_type: Data type ('cpu' or 'mem')
        :param host: Optional host name filter
        :param start_time: Start time
        :param end_time: End time
        :param sort_by_time: Sort by time
        :return: List of data dictionaries
        """
        results = OrderedDict()
    
        try:
            keys = self.redis_client.keys("*")
            for key in keys:
                try:
                    key_time = datetime.fromisoformat(key)
                    key_time = key_time.astimezone(ZoneInfo('UTC'))
                    start_time = start_time.astimezone(ZoneInfo('America/Los_Angeles'))
                    end_time = end_time.astimezone(ZoneInfo('America/Los_Angeles'))
                    if start_time and key_time < start_time:
                        continue
                    if end_time and key_time > end_time:
                        continue

                    data = self.redis_client.get(key)
                    if data:
                        data_dict = json.loads(data)
                        if host:
                            if host in data_dict:
                                dt_utc = datetime.fromisoformat(key)
                                if dt_utc.tzinfo is None:
                                    dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
                                dt_dst = dt_utc.astimezone(ZoneInfo("America/Los_Angeles"))
                                # Convert ISO timestamp to epoch timestamp
                                timestamp = int(dt_dst.timestamp())
                                results[timestamp] = data_dict[host]
                        else:
                            continue
                except ValueError:
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to get data: {str(e)}")
            raise
        if sort_by_time:
            results = OrderedDict(sorted(results.items(), key=lambda x: x[0]))
        return results


class RedisWriter(RedisBase):
    """Class for writing data to Redis"""
    
    def __init__(self, host='localhost', port=6379, db=0):
        super().__init__(host, port, db)
        self.batch_data = {}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(redis.RedisError)
    )
    @timer
    def _batch_write(self, expire_time: int = 86400 * 30) -> None:
        """Batch write data to Redis"""
        pipeline = self.redis_client.pipeline()
        try:
            for key, value in self.batch_data.items():
                try:
                    pipeline.set(key, json.dumps(value))
                    pipeline.expire(key, expire_time)
                except Exception as e:
                    logger.error(f"Failed to set key {key}: {str(e)}")
            pipeline.execute()
        except Exception as e:
            logger.error(f"Batch write failed: {str(e)}")
            pipeline.reset()
            raise

    def _get_sql_data(self, start_time: Optional[datetime] = None, 
                      end_time: Optional[datetime] = None) -> List[Dict]:
        """Get data from SQL database"""
        if start_time is None:
            start_time = date.today() - timedelta(days=1)
        if end_time is None:
            end_time = date.today() + timedelta(days=1)
        logger.info(f"Fetching SQL data from {start_time} to {end_time}")
        return self.read_sql(start_time, end_time)

    @timer
    def _data_wrangling(self):
        """Process and transform the raw data"""
        raw_dataframe = self._get_sql_data()
        return self._process_dataframe(raw_dataframe)

    def _process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process the dataframe with all necessary transformations"""
        df = df.sort_values(by='snapshot_datetime', ascending=True)
        df['rss'] = (df['rss'] / 1000000).round(2)
        df['vsz'] = (df['vsz'] / 1000000).round(2)
        df['cpu_diff'] = (df['cputimes'] - df.groupby(['host', 'pid'])['cputimes'].shift()).fillna(0)
        df['seconds_diff'] = (df['snapshot_time_epoch'] - 
                            df.groupby(['host', 'pid'])['snapshot_time_epoch'].shift()).fillna(0)
        df['cpu_norm'] = (df['cpu_diff'].div(df['seconds_diff'])).fillna(0)
        df = df[df['cpu_norm'] != 0]

        reduced = df.groupby([
            pd.Grouper(key='snapshot_datetime', freq='5min'),
            'pid', 'username', 'comm', 'bdstart', 'args', 'host'
        ]).agg({
            'rss': 'mean',
            'vsz': 'mean',
            'thcount': 'max',
            'etimes': 'max',
            'cputimes': 'max',
            'snapshot_time_epoch': 'max',
            'cpu_diff': 'max',
            'seconds_diff': 'max',
            'cpu_norm': 'mean'
        }).reset_index()

        reduced.drop(['cpu_diff', 'seconds_diff'], axis=1, inplace=True)
        return reduced

    def _process_host_data(self, df: pd.DataFrame, host: str, category: str, data_type: str, 
                          threshold: float = None) -> pd.DataFrame:
        """Process data for a specific host"""
        if category == 'cpu':
            aggre_key = 'cpu_norm'
        else:   # mem
            aggre_key = 'rss'
        df_grouped = df.groupby(['snapshot_datetime', 'host', 'comm', 'username'])[
            aggre_key].sum().reset_index()
        df_grouped = df_grouped[df_grouped[aggre_key] != 0]
        df_grouped = df_grouped[df_grouped['host'] == host]
        
        if data_type == 'command':
            result = df_grouped.groupby(['snapshot_datetime']).agg(
                {aggre_key: 'sum'}).reset_index()
        else:  # user
            result = df_grouped.groupby(['snapshot_datetime', 'username', 'comm', 'host']).agg(
                {aggre_key: 'sum'}).reset_index()
            if threshold is not None:
                result = result[result[aggre_key] > threshold]
        # fill na with 0
        result[aggre_key] = result[aggre_key].fillna(0.0)
        return result.sort_values(by='snapshot_datetime')

    @timer
    def store_data(self) -> None:
        """Process and store all data to Redis"""
        try:
            logger.info("Starting data processing and storage...")
            processed_data = self._data_wrangling()
            
            self.batch_data = {}
            self._get_cpu_load_commands_to_save(processed_data)
            self._get_cpu_load_users_to_save(processed_data)
            self._get_memory_commands_to_save(processed_data)
            self._get_memory_users_to_save(processed_data)
            
            self._batch_write()
            logger.info("Data storage completed")
            
        except Exception as e:
            logger.error(f"Error occurred during data storage: {str(e)}")
            raise

    def _get_cpu_load_commands_to_save(self, df: pd.DataFrame) -> None:
        """store the CPU load data"""
        if self.batch_data is None:
            self.batch_data = {}
            
        for host in hosts:
            top_commands = self._process_host_data(df, host, 'cpu', 'command')
            for _, row in top_commands.iterrows():
                key = f"{row['snapshot_datetime'].isoformat()}"
                host_data = self.batch_data.setdefault(key, {}).setdefault(host, {}).setdefault('cpu', {}).setdefault('command', {})
                host_data['cpu_norm'] = float(row['cpu_norm'])
                host_data['timestamp'] = row['snapshot_datetime'].isoformat()

    def _get_cpu_load_users_to_save(self, df: pd.DataFrame) -> None:
        """store the user CPU load data"""
        if self.batch_data is None:
            self.batch_data = {}
            
        for host in hosts:
            user_data = self._process_host_data(df, host, 'cpu', 'user', threshold=2)
            for _, row in user_data.iterrows():
                key = f"{row['snapshot_datetime'].isoformat()}"
                user_cpu_data = self.batch_data.setdefault(key, {}).setdefault(host, {}).setdefault('cpu', {}).setdefault('user', [])
                user_cpu_data.append({
                    'cpu_norm': float(row['cpu_norm']),
                    'username': row['username'],
                    'comm': row['comm'],
                    'host': row['host'],
                    'timestamp': row['snapshot_datetime'].isoformat()
                })

    def _get_memory_commands_to_save(self, df: pd.DataFrame) -> None:
        """store the memory data"""
        if self.batch_data is None:
            self.batch_data = {}
            
        for host in hosts:
            mem_data = self._process_host_data(df, host, 'mem', 'command')
            for _, row in mem_data.iterrows():
                key = f"{row['snapshot_datetime'].isoformat()}"
                cmd_mem_data = self.batch_data.setdefault(key, {}).setdefault(host, {}).setdefault('mem', {}).setdefault('command', {})
                cmd_mem_data['rss'] = float(row['rss'])
                cmd_mem_data['timestamp'] = row['snapshot_datetime'].isoformat()

    def _get_memory_users_to_save(self, df: pd.DataFrame) -> None:
        """store the user memory data"""
        if self.batch_data is None:
            self.batch_data = {}

        for host in hosts:
            user_data = self._process_host_data(df, host, 'mem', 'user', threshold=2)
            for _, row in user_data.iterrows():
                key = f"{row['snapshot_datetime'].isoformat()}"
                user_mem_data = self.batch_data.setdefault(key, {}).setdefault(host, {}).setdefault('mem', {}).setdefault('user', [])
                user_mem_data.append({
                    'rss': float(row['rss']),
                    'username': row['username'],
                    'comm': row['comm'],
                    'host': row['host'],
                    'timestamp': row['snapshot_datetime'].isoformat()
                })
