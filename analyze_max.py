#!/usr/bin/env python3
from sqlalchemy import create_engine

import pandas as pd
import plotly.express as px
import pickle
import dash
from flask import Flask
import dash_html_components as html
import dash_core_components as dcc
import dash_bootstrap_components as dbc

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
    ## Feature engineering: calculate the normalized difference in CPU Time (in seconds) between sampling times by unique process and host

    df['cpu_diff'] = (df['cputimes'] - df.groupby(['host', 'pid'])['cputimes'].shift()).fillna(0)

    df['seconds_diff'] = (
            df['snapshot_time_epoch'] - df.groupby(['host', 'pid'])['snapshot_time_epoch'].shift()).fillna(0)

    df['cpu_norm'] = (df['cpu_diff'].div(df['seconds_diff'])).fillna(0)
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


def show_usage_graph(df, host=None):
    df.dropna(inplace=True)
    if host is not None:
        df.drop(df[df.host != host].index, inplace=True)

    df_agg = df.groupby('snapshot_datetime'). \
        agg({'pid': 'count',
             'cpu_norm': 'sum'}). \
        reset_index().sort_values(by='snapshot_datetime', ascending=True)

    start_date = df['snapshot_datetime_date'].min()
    end_date = df['snapshot_datetime_date'].max()

    # print(df_agg2.snapshot_datetime.min())
    fig = px.line(df_agg,
                  x='snapshot_datetime',
                  y='cpu_norm',
                  title=f'Total CPU Time consumption {start_date} - {end_date} for host: {host}')
    fig.show()


def common_group(df):
    df_grouped = df.groupby(['snapshot_time_epoch', 'host', 'comm', 'username'])[
        'cpu_norm'].sum().reset_index()  # Sum the norm diff by host and process at each sampling interval
    df_grouped = df_grouped[df_grouped['cpu_norm'] != 0]  # drops where the diff = 0
    return df_grouped

def top_command(df):
    ## Feature engineering: identify the max CPU normalized difference at each sample time for each host

    top_command = common_group(df).sort_values('cpu_norm').drop_duplicates(['snapshot_time_epoch', 'host'],
                                                                           keep='last')  # Filter for max cpu diff and id the process command
    top_command.sort_values(by='snapshot_time_epoch', inplace=True)

    return top_command


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


def top_users_commands(df):
    df_max_0 = common_group(df).groupby(['snapshot_time_epoch', 'comm', 'host', 'username']).agg(
        {'cpu_norm': 'sum'}).reset_index()
    top_users_and_commands = df_max_0[df_max_0['cpu_norm'] > 2]
    return top_users_and_commands


def app_setup(df):
    global app
    app = create_app()
    TOPLEVEL_STYLE = {
        "width": "160rem"

    }
    start_date = df['snapshot_datetime_date'].min()
    end_date = df['snapshot_datetime_date'].max()

    top_users_commands_df = top_users_commands(df)
    top_command_df = top_command(df)
    fig = px.line(top_command_df,
                  x='snapshot_time_epoch',
                  y='cpu_norm',
                  title=f'Total CPU Time consumption {start_date} - {end_date}')

    main_div = html.Div(style=TOPLEVEL_STYLE,
                        className="row",
                        children=[
                            # html.Div(className="three columns", children=[sidebar_div()]),
                            html.Div(className="nine columns",
                                     style={'overflow': 'auto',
                                            'overflow': 'visible'},
                                     children=[dcc.Graph(
                                         id='example-graph',
                                         figure=fig
                                     )])
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







# show_usage_graph(df, 'rosalindf')
# top_command = top_command(df)
# top_users_and_commands = top_users_and_commands(df)

# show_usage_graph(df,'comm')
# show_usage_graph(df,'username')
def setup():

    dbfile = open('dataframe_pickle.pkl', 'rb')
    df = pickle.load(dbfile)

    #
    # df = get_process_dataframe()
    # dbfile = open('dataframe_pickle.pkl', 'ab')
    #
    # pickle.dump(df, dbfile)
    # dbfile.close()
    # sys.exit(0)

    if app is None:
        # data_setup()
        app_setup(df)


if __name__ == '__main__':
    print("Running internal server")
    setup()
    app.run_server(debug=True)
else:
    print(f"Running external server: {__name__}")
    setup()

print("exiting.")
