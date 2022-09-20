#!/usr/bin/env python3
import sys

from sqlalchemy import create_engine

import pandas as pd
import plotly.express as px
import pickle

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


def get_process_dataframe():
    host = 'ibss-central'
    database = 'load'
    user = 'root'
    password = 'qhALiqwRFNlOzwqnbXgGbKpgCZXUiSZvmAsRLlFIIMqjSQrf'
    port = 3312

    db_connection = create_engine(url="mysql+pymysql://{0}:{1}@{2}:{3}/{4}".format(
        user, password, host, port, database
    ))

    df = pd.read_sql('SELECT * FROM processes', con=db_connection)

    print(df.shape, f"\n", df.dtypes)

    df['snapshot_datetime'] = pd.to_datetime(df['snapshot_datetime'], dayfirst=True)
    df['snapshot_datetime' + str('_date')] = df['snapshot_datetime'].dt.strftime("%m/%d/%y")
    # df['snapshot_datetime' + str('_day_time')] = \
    #     df['snapshot_datetime'].dt.day_name() + \
    #     " " + \
    #     df['snapshot_datetime'].dt.strftime('%d') + \
    #     ", " + \
    #     df['snapshot_datetime'].dt.strftime('%H')

    return df


def process(df):
    # ** drop rows where username == args == args == pid == host and
    # retain the record with the highest cpu time.

    df_max_process_usage_only = df.sort_values('cputimes', ascending=False). \
        drop_duplicates(['username', 'host', 'pid'])

    df_max_process_usage_only_broken = df.drop_duplicates(['username', 'host', 'pid'])


    df_agg2 = df_max_process_usage_only.groupby(['username']). \
        agg({'pid': 'count',
             'cputimes': 'sum',
             'rss': 'sum',
             'vsz': 'sum',
             'etimes': 'sum',
             'thcount': 'sum'}). \
        reset_index(). \
        rename(columns={'cputimes': 'cputimes_sum', 'pid': 'pid_count'}). \
        sort_values(by='cputimes_sum', ascending=False)
    print(df_agg2.head())
    df_agg2 = df_agg2.head(8)
    start_date = df_max_process_usage_only['snapshot_datetime_date'].min()
    end_date = df_max_process_usage_only['snapshot_datetime_date'].max()

    # print(df_agg2.snapshot_datetime.min())
    fig = px.pie(df_agg2,
                 values='cputimes_sum',
                 names='username',
                 title=f'Total CPU Time consumption, {start_date} - {end_date}')
    fig.show()


# df = get_process_dataframe()
# dbfile = open('dataframe_pickle.pkl', 'ab')
#
# pickle.dump(df, dbfile)
# dbfile.close()
# sys.exit(0)
dbfile = open('dataframe_pickle.pkl', 'rb')
df = pickle.load(dbfile)
print("Pickle loaded...")
process(df)
