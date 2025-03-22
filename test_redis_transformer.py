import unittest
from unittest.mock import patch, MagicMock, call
import pandas as pd
import numpy as np
import redis
import json
from datetime import datetime, timedelta
from redis_transformer import RedisBase, RedisReader, RedisWriter

class TestRedisBase(unittest.TestCase):
    @patch('redis_transformer.redis.Redis')
    def test_init(self, mock_redis):
        # Test initialization with default parameters
        rb = RedisBase()
        mock_redis.assert_called_once_with(
            host='localhost', 
            port=6379, 
            db=0, 
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )
        
        # Test initialization with custom parameters
        rb = RedisBase(host='testhost', port=1234, db=5)
        mock_redis.assert_called_with(
            host='testhost', 
            port=1234, 
            db=5, 
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )
    
    @patch('redis_transformer.create_engine')
    @patch('redis_transformer.pd.read_sql')
    def test_read_sql(self, mock_read_sql, mock_create_engine):
        # Setup mock
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_df = pd.DataFrame({'data': [1, 2, 3]})
        mock_read_sql.return_value = mock_df
        
        # Test with default parameters
        rb = RedisBase()
        result = rb.read_sql()
        
        # Verify engine creation and SQL query
        mock_create_engine.assert_called_once()
        mock_read_sql.assert_called_once()
        self.assertEqual(result.equals(mock_df), True)
        
        # Test with custom date parameters
        start_date = '2023-01-01 00:00:00'
        end_date = '2023-01-02 00:00:00'
        result = rb.read_sql(start_date, end_date)
        
        # Verify SQL query with date parameters
        self.assertEqual(mock_read_sql.call_count, 2)
        self.assertEqual(result.equals(mock_df), True)


class TestRedisReader(unittest.TestCase):
    @patch('redis_transformer.redis.Redis')
    def setUp(self, mock_redis):
        self.mock_redis_client = MagicMock()
        mock_redis.return_value = self.mock_redis_client
        self.redis_reader = RedisReader()
    
    def test_get_data_empty(self):
        # Test with empty keys
        self.mock_redis_client.keys.return_value = []
        result = self.redis_reader.get_data()
        self.assertEqual(len(result), 0)
    
    def test_get_data_with_host_filter(self):
        # Setup mock data
        timestamp = datetime.now().replace(microsecond=0)
        iso_timestamp = timestamp.isoformat()
        epoch_timestamp = int(timestamp.timestamp())
        
        self.mock_redis_client.keys.return_value = [iso_timestamp]
        self.mock_redis_client.get.return_value = json.dumps({
            'flor': {'cpu': {'command': {'cpu_norm': 10.5}}}
        })
        
        # Test with host filter
        result = self.redis_reader.get_data(host='flor')
        
        # Verify result
        self.assertEqual(len(result), 1)
        self.assertEqual(result[epoch_timestamp]['cpu']['command']['cpu_norm'], 10.5)
    
    def test_get_data_with_time_range(self):
        # Setup mock data
        now = datetime.now().replace(microsecond=0)
        past = now - timedelta(hours=2)
        future = now + timedelta(hours=2)
        
        timestamps = [
            past.isoformat(),
            now.isoformat(),
            future.isoformat()
        ]
        
        self.mock_redis_client.keys.return_value = timestamps
        
        # Mock get method to return different data for each timestamp
        def mock_get(key):
            if key == past.isoformat():
                return json.dumps({'flor': {'cpu': {'command': {'cpu_norm': 5.0}}}})
            elif key == now.isoformat():
                return json.dumps({'flor': {'cpu': {'command': {'cpu_norm': 10.0}}}})
            elif key == future.isoformat():
                return json.dumps({'flor': {'cpu': {'command': {'cpu_norm': 15.0}}}})
        
        self.mock_redis_client.get = mock_get
        
        # Test with time range (only past and now)
        result = self.redis_reader.get_data(
            host='flor',
            start_time=past - timedelta(minutes=5),
            end_time=now + timedelta(minutes=5)
        )
        
        # Verify result (should only include past and now)
        self.assertEqual(len(result), 2)
        self.assertTrue(int(past.timestamp()) in result)
        self.assertTrue(int(now.timestamp()) in result)
        self.assertFalse(int(future.timestamp()) in result)


class TestRedisWriter(unittest.TestCase):
    @patch('redis_transformer.redis.Redis')
    def setUp(self, mock_redis):
        self.mock_redis_client = MagicMock()
        mock_redis.return_value = self.mock_redis_client
        self.redis_writer = RedisWriter()
    
    @patch('redis_transformer.RedisWriter._get_sql_data')
    @patch('redis_transformer.RedisWriter._process_dataframe')
    def test_data_wrangling(self, mock_process_df, mock_get_sql):
        # Setup mocks
        mock_df = pd.DataFrame({'data': [1, 2, 3]})
        mock_get_sql.return_value = mock_df
        mock_process_df.return_value = mock_df
        
        # Call method
        result = self.redis_writer._data_wrangling()
        
        # Verify calls
        mock_get_sql.assert_called_once()
        mock_process_df.assert_called_once_with(mock_df)
        self.assertEqual(result.equals(mock_df), True)
    
    def test_process_dataframe(self):
        # Create test dataframe
        df = pd.DataFrame({
            'snapshot_datetime': pd.date_range(start='2023-01-01', periods=3, freq='H'),
            'host': ['flor', 'flor', 'flor'],
            'pid': [123, 123, 123],
            'username': ['user1', 'user1', 'user1'],
            'comm': ['cmd1', 'cmd1', 'cmd1'],
            'bdstart': ['start1', 'start1', 'start1'],
            'args': ['arg1', 'arg1', 'arg1'],
            'rss': [1000000, 2000000, 3000000],
            'vsz': [4000000, 5000000, 6000000],
            'thcount': [1, 2, 3],
            'etimes': [100, 200, 300],
            'cputimes': [10, 20, 30],
            'snapshot_time_epoch': [1000, 2000, 3000]
        })
        
        # Process dataframe
        result = self.redis_writer._process_dataframe(df)
        
        # Verify results
        self.assertFalse(result.empty)
        self.assertEqual(result['rss'].iloc[0], 2.0)  # Converted to GB
        self.assertEqual(result['vsz'].iloc[0], 5.0)  # Converted to GB
        self.assertTrue('cpu_norm' in result.columns)
        self.assertFalse('cpu_diff' in result.columns)  # Should be dropped
    
    @patch('redis_transformer.RedisWriter._batch_write')
    @patch('redis_transformer.RedisWriter._data_wrangling')
    @patch('redis_transformer.RedisWriter._get_cpu_load_commands_to_save')
    @patch('redis_transformer.RedisWriter._get_cpu_load_users_to_save')
    @patch('redis_transformer.RedisWriter._get_memory_commands_to_save')
    @patch('redis_transformer.RedisWriter._get_memory_users_to_save')
    def test_store_data(self, mock_mem_users, mock_mem_cmds, 
                        mock_cpu_users, mock_cpu_cmds, 
                        mock_data_wrangling, mock_batch_write):
        # Setup mock
        mock_df = pd.DataFrame({'data': [1, 2, 3]})
        mock_data_wrangling.return_value = mock_df
        
        # Call method
        self.redis_writer.store_data()
        
        # Verify all methods were called
        mock_data_wrangling.assert_called_once()
        mock_cpu_cmds.assert_called_once_with(mock_df)
        mock_cpu_users.assert_called_once_with(mock_df)
        mock_mem_cmds.assert_called_once_with(mock_df)
        mock_mem_users.assert_called_once_with(mock_df)
        mock_batch_write.assert_called_once()
    
    def test_batch_write(self):
        # Setup test data
        self.redis_writer.batch_data = {
            '2023-01-01T00:00:00': {
                'flor': {
                    'cpu': {
                        'command': {'cpu_norm': 10.5}
                    }
                }
            }
        }
        
        # Setup mock pipeline
        mock_pipeline = MagicMock()
        self.mock_redis_client.pipeline.return_value = mock_pipeline
        
        # Call method
        self.redis_writer._batch_write()
        
        # Verify pipeline operations
        mock_pipeline.set.assert_called_once()
        mock_pipeline.expire.assert_called_once()
        mock_pipeline.execute.assert_called_once()
    
    def test_process_host_data_cpu(self):
        # Create test dataframe
        df = pd.DataFrame({
            'snapshot_datetime': pd.date_range(start='2023-01-01', periods=3, freq='H'),
            'host': ['flor', 'flor', 'alice'],
            'username': ['user1', 'user2', 'user1'],
            'comm': ['cmd1', 'cmd2', 'cmd1'],
            'cpu_norm': [10.5, 20.5, 30.5],
            'rss': [1.0, 2.0, 3.0]
        })
        
        # Process CPU data for 'flor'
        result = self.redis_writer._process_host_data(df, 'flor', 'cpu', 'command')
        
        # Verify results
        self.assertEqual(len(result), 2)  # Only 'flor' entries
        self.assertEqual(result['cpu_norm'].sum(), 31.0)  # 10.5 + 20.5
    
    def test_process_host_data_memory(self):
        # Create test dataframe
        df = pd.DataFrame({
            'snapshot_datetime': pd.date_range(start='2023-01-01', periods=3, freq='H'),
            'host': ['flor', 'flor', 'alice'],
            'username': ['user1', 'user2', 'user1'],
            'comm': ['cmd1', 'cmd2', 'cmd1'],
            'cpu_norm': [10.5, 20.5, 30.5],
            'rss': [1.0, 2.0, 3.0]
        })
        
        # Process memory data for 'flor' with threshold
        result = self.redis_writer._process_host_data(df, 'flor', 'mem', 'user', threshold=1.5)
        
        # Verify results
        self.assertEqual(len(result), 1)  # Only entries above threshold
        self.assertEqual(result['rss'].iloc[0], 2.0)  # Only the 2.0 value is above threshold


if __name__ == '__main__':
    unittest.main() 