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

    return df


def show_usage_graph(df, by="username"):
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


def time_series(df):
    # time_samples = df['snapshot_time_epoch'].unique()
    # print(f"{time_samples}")
    time_slots = df.sort_values('snapshot_time_epoch', ascending=True).groupby(['snapshot_time_epoch'])
    prev_slot = None
    new_df = df
    new_df['elapsed_time'] = 0
    new_df.set_index(['pid','host','snapshot_time_epoch'])
    for epoch_time, time_slot_epoch in time_slots:
        if prev_slot is not None:
            merged = pd.merge(prev_slot[['pid', 'host', 'cputimes']],
                              time_slot_epoch[['pid', 'host', 'cputimes', 'snapshot_time_epoch']],
                              how='right',
                              on=['pid', 'host'],
                              suffixes=('_prev', '_cur')
                              )
            merged['elapsed_time'] = merged['cputimes_cur'] - merged['cputimes_prev']
            merged.drop('cputimes_cur', axis=1, inplace=True)
            merged.drop('cputimes_prev', axis=1, inplace=True)
            merged.set_index(['pid', 'host', 'snapshot_time_epoch'])
            merged = merged[merged.elapsed_time != 0]
            # new_df = pd.merge(new_df,
            #                   merged[['pid', 'snapshot_time_epoch', 'host', 'elapsed_time']],
            #                   how='right',
            #                   on=['pid', 'snapshot_time_epoch', 'host']
            #                   )
            new_df = new_df.combine_first(merged)

            print(f"df")
        prev_slot = time_slot_epoch

    print(f"{df.head(5)}")
    print(f"{df.info()}")
    # for time_sample in time_samples:
    #     print(f"time sample: {time_sample}")
    print(f"done.")


# df = get_process_dataframe()
# dbfile = open('dataframe_pickle.pkl', 'ab')
#
# pickle.dump(df, dbfile)
# dbfile.close()
# sys.exit(0)
dbfile = open('dataframe_pickle.pkl', 'rb')
df = pickle.load(dbfile)
print("Pickle loaded...")
# show_usage_graph(df,'comm')
# show_usage_graph(df,'username')
time_series(df)
