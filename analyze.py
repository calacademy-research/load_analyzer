#!/usr/bin/env python3
from sqlalchemy import create_engine

import pandas as pd
import pickle
import os

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
    df = None
    reduced = None
    PICKLE_FILE = './app/dataframe_pickle.pkl'

    def __init__(self, use_tsv=True, use_pickle=False):


        if not os.path.exists(self.PICKLE_FILE) or use_pickle is False:

            print("Creating a new pickle cache...")
            if use_tsv:
                initial_df = self.read_tsv()
            else:
                initial_df = self.read_sql()
            self.initial_data_wrangling(initial_df)
            self.df = self.reduced
            if use_pickle :
                print(f"Writing pickle file: {self.PICKLE_FILE}")
                dbfile = open(self.PICKLE_FILE, 'ab')

                pickle.dump(self.df, dbfile)
                dbfile.close()
                print(f"Pickle write complete.")

        else:
            print(f"Loading pickle file: {self.PICKLE_FILE}")
            dbfile = open(self.PICKLE_FILE, 'rb')
            self.df = pickle.load(dbfile)
            # print(df.shape, f"\n", df.dtypes)

    def read_sql(self):
        # host = 'ibss-central'
        host = '10.1.10.123'
        database = 'load'
        user = 'root'
        password = 'qhALiqwRFNlOzwqnbXgGbKpgCZXUiSZvmAsRLlFIIMqjSQrf'
        port = 3312

        db_connection = create_engine(url="mysql+pymysql://{0}:{1}@{2}:{3}/{4}".format(
            user, password, host, port, database
        ))
        print("connected to database...")
        df = pd.read_sql('SELECT * FROM processes', con=db_connection)

        # print(df.shape, f"\n", df.dtypes)
        print("db read compelte.")

        return df

    ## *****ReadTSV******** Hadrien's contribution ********************
    def read_tsv(self):
        filepath = './processes.tsv'

        col_Names = ['pid', 'username', 'comm', 'cputimes', 'rss', 'vsz', 'thcount', 'etimes', 'bdstart', 'args',
                     'snapshot_time_epoch', 'snapshot_datetime', 'host']  # from processes.tsv
        df = pd.read_csv(filepath, float_precision=None, sep='\t', header=0, names=col_Names)

        # print(df.shape, f"\n", df.dtypes)

        return df

    def initial_data_wrangling(self, raw_dataframe):
        df = raw_dataframe

        df['snapshot_datetime'] = pd.to_datetime(df['snapshot_datetime'], dayfirst=True)
        df['snapshot_datetime' + str('_date')] = df['snapshot_datetime'].dt.strftime("%m/%d/%y")
        df['snapshot_datetime' + str('_daytime')] = df['snapshot_datetime'].dt.day_name() + " " + df[
            'snapshot_datetime'].dt.strftime('%d') + ", " + df['snapshot_datetime'].dt.strftime('%H')
        df = df.sort_values(by='snapshot_datetime', ascending=True)
        ## Converting bytes to Gb for rss and vsz
        df['rss'] = (df['rss'] / 1000000).round(2)
        df['vsz'] = (df['vsz'] / 1000000).round(2)
        ## This needs to happen before aggregating by time, otherwise the values will become distored (we're normalizing by seconds)
        df['cpu_diff'] = (df['cputimes'] - df.groupby(['host', 'pid'])['cputimes'].shift()).fillna(0)
        df['seconds_diff'] = (
                df['snapshot_time_epoch'] - df.groupby(['host', 'pid'])['snapshot_time_epoch'].shift()).fillna(0)
        df['cpu_norm'] = (df['cpu_diff'].div(df['seconds_diff'])).fillna(0)
        df = df[df['cpu_norm'] != 0]  ## Filtering out all rows where cpu_norm = 0.

        ## Aggregating sampling time by 15 min; since snapshot_time_epoch correspond to discrete sampling point, I retained the max snapshot_time_epoch.
        reduced = df.groupby(
            [pd.Grouper(key='snapshot_datetime', freq='15min'), 'pid', 'username', 'comm', 'bdstart', 'args',
             'host']).agg(
            {'rss': 'mean', 'vsz': 'mean', 'thcount': 'max', 'etimes': 'max', 'cputimes': 'max',
             'snapshot_time_epoch': 'max',
             'cpu_diff': 'max', 'seconds_diff': 'max', 'cpu_norm': 'mean'}).reset_index()

        reduced.drop(['cpu_diff', 'seconds_diff'], axis=1, inplace=True)  ## Removing redundant fields
        df.drop(['cpu_diff', 'seconds_diff'], axis=1, inplace=True)  ## Removing redundant fields

        self.df = df
        self.reduced = reduced

    # def usage(self, df, host=None):
    #     df.dropna(inplace=True)
    #     if host is not None:
    #         df.drop(df[df.host != host].index, inplace=True)
    #
    #     df_agg = df.groupby('snapshot_datetime'). \
    #         agg({'pid': 'count',
    #              'cpu_norm': 'sum'}). \
    #         reset_index().sort_values(by='snapshot_datetime', ascending=True)
    #
    #     return df_agg

    def top_load_command(self, limit_to_host=None):
        ## Feature engineering: identify the max CPU normalized difference at each sample time for each host

        top_command = self.common_group_load(limit_to_host).sort_values('cpu_norm').drop_duplicates(
            ['snapshot_datetime',
             'host'],
            keep='last')  # Filter for max cpu diff and id the process command
        top_command.sort_values(by='snapshot_datetime', inplace=True)

        return top_command

    def top_memory_command(self, limit_to_host=None):
        ## Feature engineering: identify the max CPU normalized difference at each sample time for each host

        top_command = self.common_group_memory(limit_to_host).sort_values('rss').drop_duplicates(['snapshot_datetime',
                                                                                                  'host'],
                                                                                                 keep='last')  # Filter for max cpu diff and id the process command
        top_command.sort_values(by='snapshot_datetime', inplace=True)

        return top_command

    def top_users_memory_commands(self, limit_to_host=None):
        df_max_0 = self.common_group_memory(limit_to_host).groupby(
            ['snapshot_datetime', 'comm', 'host', 'username']).agg(
            {'rss': 'sum'}).reset_index()
        top_users_and_commands = df_max_0[df_max_0['rss'] > 2]

        return top_users_and_commands

    def top_users_load_commands(self, limit_to_host=None):
        df_max_0 = self.common_group_load(limit_to_host).groupby(['snapshot_datetime', 'comm', 'host', 'username']).agg(
            {'cpu_norm': 'sum'}).reset_index()
        top_users_and_commands = df_max_0[df_max_0['cpu_norm'] > 2]

        return top_users_and_commands

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
