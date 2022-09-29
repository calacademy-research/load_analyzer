#!/usr/bin/env python3
from sqlalchemy import create_engine

import pandas as pd
import plotly.express as px
import pickle
from dash import Dash, dcc, html, Input, Output
import dash
from flask import Flask
import dash_html_components as html
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import numpy as np
import sys
import os

app = None

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


def read_sql():
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
    return df


## *****ReadTSV******** Hadrien's contribution ********************
def read_tsv():
    filepath = './processes.tsv'

    col_Names = ['pid', 'username', 'comm', 'cputimes', 'rss', 'vsz', 'thcount', 'etimes', 'bdstart', 'args',
                 'snapshot_time_epoch', 'snapshot_datetime', 'host']  # from processes.tsv
    df = pd.read_csv(filepath, float_precision=None, sep='\t', header=0, names=col_Names)

    print(df.shape, f"\n", df.dtypes)

    return df


def initial_data_wrangling(raw_dataframe):
    df = raw_dataframe

    df['snapshot_datetime'] = pd.to_datetime(df['snapshot_datetime'], dayfirst=True)
    df['snapshot_datetime' + str('_date')] = df['snapshot_datetime'].dt.strftime("%m/%d/%y")
    df['snapshot_datetime' + str('_daytime')] = df['snapshot_datetime'].dt.day_name() + " " + df[
        'snapshot_datetime'].dt.strftime('%d') + ", " + df['snapshot_datetime'].dt.strftime('%H')
    df = df.sort_values(by='snapshot_datetime', ascending=True)
    ## Converting bytes to Gb for rss and vsz
    df['rss'] = (df['rss'] / 1000000000).round(2)
    df['vsz'] = (df['vsz'] / 1000000000).round(2)
    ## This needs to happen before aggregating by time, otherwise the values will become distored (we're normalizing by seconds)
    df['cpu_diff'] = (df['cputimes'] - df.groupby(['host', 'pid'])['cputimes'].shift()).fillna(0)
    df['seconds_diff'] = (
                df['snapshot_time_epoch'] - df.groupby(['host', 'pid'])['snapshot_time_epoch'].shift()).fillna(0)
    df['cpu_norm'] = (df['cpu_diff'].div(df['seconds_diff'])).fillna(0)
    ## Aggregating sampling time by 15 min; since snapshot_time_epoch correspond to discrete sampling point, I retained the max snapshot_time_epoch.
    df = df.groupby(
        [pd.Grouper(key='snapshot_datetime', freq='15min'), 'pid', 'username', 'comm', 'bdstart', 'args', 'host']).agg(
        {'rss': 'sum', 'vsz': 'sum', 'thcount': 'sum', 'etimes': 'sum', 'cputimes': 'sum', 'snapshot_time_epoch': 'max',
         'cpu_diff': 'sum', 'seconds_diff': 'sum', 'cpu_norm': 'sum'}).reset_index()
    df = df[df['cpu_norm'] != 0]  ## Filtering out all rows where cpu_norm = 0.

    df.drop(['cpu_diff', 'seconds_diff'], axis=1, inplace=True)  ## Removing redundant fields

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

    # hadrien's agg
    # # This returns comm with the max cpu_norm for each host and at each sampling instance.
    # test = df_bar_d.sort_values('cpu_norm').drop_duplicates(['snapshot_time_epoch', 'host'], keep='last')
    # test.sort_values(by='snapshot_time_epoch', inplace=True)

    df_agg = df_agg.head(8)
    start_date = df_max_process_usage_only['snapshot_datetime_date'].min()
    end_date = df_max_process_usage_only['snapshot_datetime_date'].max()

    # print(df_agg2.snapshot_datetime.min())
    fig = px.pie(df_agg,
                 values='cputimes_sum',
                 names=by,

                 title=f'Total CPU Time consumption by {by}, {start_date} - {end_date}')
    fig.show()


def common_group(df):
    df_grouped = df.groupby(['snapshot_datetime', 'host', 'comm', 'username'])[
        'cpu_norm'].sum().reset_index()  # Sum the norm diff by host and process at each sampling interval
    df_grouped = df_grouped[df_grouped['cpu_norm'] != 0]  # drops where the diff = 0
    return df_grouped


def usage(df, host=None):
    df.dropna(inplace=True)
    if host is not None:
        df.drop(df[df.host != host].index, inplace=True)

    df_agg = df.groupby('snapshot_datetime'). \
        agg({'pid': 'count',
             'cpu_norm': 'sum'}). \
        reset_index().sort_values(by='snapshot_datetime', ascending=True)

    return df_agg


def top_command(df):
    ## Feature engineering: identify the max CPU normalized difference at each sample time for each host

    top_command = common_group(df).sort_values('cpu_norm').drop_duplicates(['snapshot_datetime', 'host'],
                                                                           keep='last')  # Filter for max cpu diff and id the process command
    top_command.sort_values(by='snapshot_datetime', inplace=True)

    return top_command


def top_users_commands(df):
    df_max_0 = common_group(df).groupby(['snapshot_datetime', 'comm', 'host', 'username']).agg(
        {'cpu_norm': 'sum'}).reset_index()
    top_users_and_commands = df_max_0[df_max_0['cpu_norm'] > 2]
    return top_users_and_commands


def create_app():
    external_stylesheets = [dbc.themes.BOOTSTRAP, 'https://codepen.io/chriddyp/pen/bWLwgP.css']
    global server
    server = Flask(__name__)

    app = dash.Dash(__name__,
                    title='Load analyzer',
                    prevent_initial_callbacks=True,
                    external_stylesheets=external_stylesheets,
                    server=server)

    return app


def sidebar_div(df):
    global app

    SIDEBAR_STYLE = {
        "position": "fixed",
        "top": 0,
        "left": 0,
        "bottom": 0,
        "width": 150,
        "backgroundColor": "#F5F5F5",
        "padding": "2rem 1rem"
    }

    @app.callback(
        Output('dd-output-container', 'children'),
        Input('demo-dropdown', 'value')
    )
    def update_output(value):
        return f'You have selected {value}'

    server_array = df['host'].unique()
    server_select_dropdown = html.Div([dcc.Dropdown(server_array, server_array[0], id='demo-dropdown'),
                                       html.Div(id='dd-output-container')])
    return (html.Div(id='sidebar',
                     style=SIDEBAR_STYLE,
                     children=[server_select_dropdown]))


def load_graph_one_server(hostname):
    pass

def main_content_div(df):
    top_users_commands_df = top_users_commands(df)

    top_command_df = top_command(df)

    fig = go.Figure()
    all_tuples = []

    for index, row in top_command_df.iterrows():
        entry = ''
        cur_datetime = row['snapshot_datetime']
        tops = top_users_commands_df[top_users_commands_df['snapshot_datetime'] == cur_datetime].sort_values(
            by='cpu_norm', ascending=False)
        for sindex, srow in tops.iterrows():
            entry += f"<br>Host: {srow['host']} username: {srow['username']} load: {srow['cpu_norm']} command: {srow['comm']}"

        all_tuples.append(entry)

    # customdata = np.stack((top_command_df['host'], top_command_df['username'], top_command_df['cpu_norm']), axis=-1)
    # customdata = np.stack(top_command_df['username'], axis=-1)

    customdata = np.stack(all_tuples, axis=-1)

    trace = go.Scatter(
        mode='lines',
        x=top_command_df['snapshot_datetime'],
        y=top_command_df['cpu_norm'],
        customdata=customdata,
        hovertemplate=('<br><b>Time:</b>: %{x}<br>' + \
                       '<i>Total load</i>: %{y:.2f}' + \
                       '<br>%{customdata}'
                       ),
        line=dict(
            color="blue",
            width=1
        )
    )

    fig.add_trace(trace)

    graph = dcc.Graph(id='example-graph', figure=fig)
    return graph


def app_setup(df):
    global app
    app = create_app()
    TOPLEVEL_STYLE = {
        "width": "160rem"

    }
    # start_date = df['snapshot_datetime_date'].min()
    # end_date = df['snapshot_datetime_date'].max()

    main_div = html.Div(style=TOPLEVEL_STYLE,
                        className="row",
                        children=[
                            html.Div(className="two columns", children=[sidebar_div(df)]),
                            html.Div(className="right columns",
                                     style={'overflow': 'auto',
                                            'overflow': 'visible'},
                                     children=[main_content_div(df)]
                                     )
                        ])

    app.layout = html.Div(
        children=
        [
            dcc.Input(id="loading-input-2",
                      style={"visibility": "hidden"},
                      value='Input triggers nested spinner'),
            dcc.Loading(
                id="loading-2",
                fullscreen=True,

                children=[html.Div([html.Div(id="loading-output-2")]),
                          main_div],
                type="circle",
            )
        ]
    )


def setup(use_tsv=True):
    PICKLE_FILE = './dataframe_pickle.pkl'
    if not os.path.exists(PICKLE_FILE):

        print("CREATING NEW PKL CACHE")
        if use_tsv:
            df = read_tsv()
        else:
            df = read_sql()
        df = initial_data_wrangling(df)
        dbfile = open(PICKLE_FILE, 'ab')

        pickle.dump(df, dbfile)
        dbfile.close()
    else:
        dbfile = open(PICKLE_FILE, 'rb')
        df = pickle.load(dbfile)
        print(df.shape, f"\n", df.dtypes)

    if app is None:
        app_setup(df)
        print("App is set up.")


if __name__ == '__main__':
    setup(False)
    print("Running internal server...")
    app.run_server(debug=True)
else:
    print(f"Running external server: {__name__}")
    setup()

print("exiting.")
