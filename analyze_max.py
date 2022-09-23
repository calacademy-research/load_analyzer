#!/usr/bin/env python3
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
    df.sort_values(by='snapshot_datetime', inplace=True)
    df['cpu_diff'] = df['cputimes'] - df.groupby(['host', 'pid'])['cputimes'].shift()
    return df


# Arguments are 'comm' for by-command and 'username' (default) for by-user
def show_percent_usage_by(df, by="username"):
    # ** drop rows where username == args == pid == host and
    # retain the record with the highest cpu time.

    # Sort so that we choose only the highest value (i.e. final)
    # cputime. Cputime is cumulative (inherent in the output of linux)
    df_max_process_usage_only = df.sort_values('cputimes', ascending=False). \
        drop_duplicates(['username', 'host', 'pid'])

    df_agg = df_max_process_usage_only.groupby([by]). \
        agg({'pid': 'count',
             'cputimes': 'sum',
             'rss': 'sum',
             'vsz': 'sum',
             'etimes': 'sum',
             'thcount': 'sum'}). \
        reset_index(). \
        rename(columns={'cputimes': 'cputimes_sum', 'pid': 'pid_count'}). \
        sort_values(by='cputimes_sum', ascending=False)
    # print(df_agg2.head())
    df_agg = df_agg.head(8)
    start_date = df_max_process_usage_only['snapshot_datetime_date'].min()
    end_date = df_max_process_usage_only['snapshot_datetime_date'].max()

    # print(df_agg2.snapshot_datetime.min())
    fig = px.pie(df_agg,
                 values='cputimes_sum',
                 names=by,
                 title=f'Total CPU Time consumption by {by}, {start_date} - {end_date}')
    fig.show()


def show_usage_graph(df):
    df_agg = df.groupby('snapshot_datetime'). \
        agg({'pid': 'count',
             'cpu_diff': 'sum'}). \
        reset_index().sort_values(by='snapshot_datetime', ascending=True)
        # rename(columns={'cputimes': 'cputimes_sum', 'pid': 'pid_count'}). \

    # print(df_agg2.head())
    # df_agg = df_agg.head(8)
    start_date = df['snapshot_datetime_date'].min()
    end_date = df['snapshot_datetime_date'].max()

    # print(df_agg2.snapshot_datetime.min())
    fig = px.line(df_agg,
                  x='snapshot_datetime',
                  y='cpu_diff',
                  title=f'Total CPU Time consumption {start_date} - {end_date}')
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
show_usage_graph(df)
# show_usage_graph(df,'comm')
# show_usage_graph(df,'username')
