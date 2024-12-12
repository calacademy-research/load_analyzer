#!/usr/bin/env python3
from sqlalchemy import create_engine

import pandas as pd
import pickle
import os
import datetime
from app.config import DB_CONFIG

'''
    PID: The process ID (every process is assigned a number as an ID).
    Username: unique users on the servers
    comm: command name
    cputimes:   CPU time seconds; the measurement of the length of time that data is 
                being worked on by the processor and is used as an indicator of 
                how much processing is required for a process or how CPU intensive 
                a process or program is .
    rss:    Resident Set Size (measured in bytes); this is the size of memory that a 
            process has currently used to load all of its pages .
    vsz:    Virtual Memory Size (measured in bytes); this is the size of memory 
            that Linux has given to a process, but it 
            doesn’t necessarily mean that the process is using all of that memory .
    thcount: Thread count
    etimes: elapsed time in seconds, i.e. wall-clock time (the actual time 
            taken from the start of a computer program to the end). 
    bdstart: start time
    args: full command
    snapshot_time_epoch
    snapshot_datetime
    host: servers
'''


class Analyze():
    _instance = None
    df = None
    reduced = None
    PICKLE_FILE = './app/dataframe_pickle.pkl'

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Analyze, cls).__new__(cls)
        return cls._instance

    def __init__(self, use_tsv=True, use_pickle=False):
        if not hasattr(self, 'initialized'):  # This ensures initialization happens only once
            self.initialized = True
            if not os.path.exists(self.PICKLE_FILE) or use_pickle is False:
                print("Reading data, cache file not found...")
                if use_tsv:
                    print("Reading from TSV")
                    initial_df = self.read_tsv()
                else:
                    print("Reading from Database")
                    initial_df = self.read_sql()
                self.initial_data_wrangling(initial_df)
                self.df = self.reduced
                if use_pickle:
                    print(f"Writing pickle file: {self.PICKLE_FILE}")
                    with open(self.PICKLE_FILE, 'ab') as dbfile:
                        pickle.dump(self.df, dbfile)
                    print("Pickle write complete.")
            else:
                print(f"Loading pickle file: {self.PICKLE_FILE}")
                with open(self.PICKLE_FILE, 'rb') as dbfile:
                    self.df = pickle.load(dbfile)

    def update_df(self, start_date=None, end_date=None):
        initial_df = self.read_sql(start_date, end_date)
        self.initial_data_wrangling(initial_df)
        self.df = self.reduced

    def read_sql(self, start_date=None, end_date=None):
        if start_date is None:
            start_date = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime('%Y-%m-%d')
        if end_date is None:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d')

        db_connection = create_engine(url="mysql+pymysql://{0}:{1}@{2}:{3}/{4}".format(
            DB_CONFIG['user'],
            DB_CONFIG['password'],
            DB_CONFIG['host'],
            DB_CONFIG['port'],
            DB_CONFIG['database']
        ))
        print(f"connected to database on {DB_CONFIG['host']}...")

        sql_string = f"SELECT * FROM processes WHERE snapshot_datetime BETWEEN '{start_date} 00:00:00' AND '{end_date} 23:59:59'"
        print(f"Reading using sql: {sql_string}")

        df = pd.read_sql(sql_string, con=db_connection)
        print("db read complete.")
        return df

    def read_tsv(self):
        filepath = './processes.tsv'
        df = pd.read_csv(filepath, float_precision=None, sep='\t', header=0)
        return df

    def initial_data_wrangling(self, raw_dataframe):
        df = raw_dataframe.sort_values(by='snapshot_datetime', ascending=True)
        ## Converting bytes to Gb for rss and vsz
        df['rss'] = (df['rss'] / 1000000).round(2)
        df['vsz'] = (df['vsz'] / 1000000).round(2)
        ## This needs to happen before aggregating by time, otherwise the values will become distored (we're normalizing by seconds)
        df['cpu_diff'] = (df['cputimes'] - df.groupby(['host', 'pid'])['cputimes'].shift()).fillna(0)
        df['seconds_diff'] = (
                    df['snapshot_time_epoch'] - df.groupby(['host', 'pid'])['snapshot_time_epoch'].shift()).fillna(0)
        df['cpu_norm'] = (df['cpu_diff'].div(df['seconds_diff'])).fillna(0)
        df = df[df['cpu_norm'] != 0]  ## Filtering out all rows where cpu_norm = 0.

        ## Aggregating sampling time by 5 min; since snapshot_time_epoch correspond to discrete sampling point, I retained the max snapshot_time_epoch.
        reduced = df.groupby(
            [pd.Grouper(key='snapshot_datetime', freq='5min'), 'pid', 'username', 'comm', 'bdstart', 'args',
             'host']).agg(
            {'rss': 'mean', 'vsz': 'mean', 'thcount': 'max', 'etimes': 'max', 'cputimes': 'max',
             'snapshot_time_epoch': 'max',
             'cpu_diff': 'max', 'seconds_diff': 'max', 'cpu_norm': 'mean'}).reset_index()

        reduced.drop(['cpu_diff', 'seconds_diff'], axis=1, inplace=True)  ## Removing redundant fields
        df.drop(['cpu_diff', 'seconds_diff'], axis=1, inplace=True)  ## Removing redundant fields

        self.df = df
        self.reduced = reduced

    def top_load_commands(self, limit_to_host=None):
        top_commands = self.common_group_load(limit_to_host).groupby(['snapshot_datetime']).agg(
            {'cpu_norm': 'sum'}).reset_index()
        top_commands.sort_values(by='snapshot_datetime', inplace=True)

        return top_commands

    def top_load_users(self, limit_to_host=None):
        df_max_0 = self.common_group_load(limit_to_host).groupby(['snapshot_datetime', 'comm', 'host', 'username']).agg(
            {'cpu_norm': 'sum'}).reset_index()
        top_users = df_max_0[df_max_0['cpu_norm'] > 2]

        return top_users

    def top_memory_commands(self, limit_to_host=None):
        top_commands = self.common_group_memory(limit_to_host).groupby(['snapshot_datetime', 'host']).agg(
            {'rss': 'sum'}).reset_index()
        top_commands.sort_values(by='snapshot_datetime', inplace=True)

        return top_commands
    
    def top_memory_users(self, limit_to_host=None):
        df_max_0 = self.common_group_memory(limit_to_host).groupby(
            ['snapshot_datetime', 'comm', 'host', 'username']).agg(
            {'rss': 'sum'}).reset_index()
        top_users = df_max_0[df_max_0['rss'] > 2]

        return top_users

    def common_group_memory(self, limit_to_host=None):
        df_grouped = self.df.groupby(['snapshot_datetime', 'host', 'comm', 'username'])[
            'rss'].sum().reset_index()  # Sum the norm diff by host and process at each sampling interval
        if limit_to_host is not None:
            df_grouped = df_grouped[df_grouped['host'] == limit_to_host]

        return df_grouped

    def common_group_load(self, limit_to_host=None):
        df_grouped = self.df.groupby(['snapshot_datetime', 'host', 'comm', 'username'])[
            'cpu_norm'].sum().reset_index()  # Sum the norm diff by host and process at each sampling interval
        df_grouped = df_grouped[df_grouped['cpu_norm'] != 0]  # drops where the diff = 0
        if limit_to_host is not None:
            df_grouped = df_grouped[df_grouped['host'] == limit_to_host]

        return df_grouped
