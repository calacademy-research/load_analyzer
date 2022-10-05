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
    app = None
    SIDEBAR_WIDTH = "150px"

    def read_sql(self):
        host = 'ibss-central'
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
        df['rss'] = (df['rss'] / 10000000).round(2)
        df['vsz'] = (df['vsz'] / 10000000).round(2)
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
    def show_percent_usage_by(self, df, by="username"):
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


    def common_group_memory(self, df, limit_to_host=None):
        df_grouped = df.groupby(['snapshot_datetime', 'host', 'comm', 'username'])[
            'rss'].sum().reset_index()  # Sum the norm diff by host and process at each sampling interval
        if limit_to_host is not None:
            df_grouped = df_grouped[df_grouped['host'] == limit_to_host]

        return df_grouped


    def common_group_load(self, df, limit_to_host=None):
        df_grouped = df.groupby(['snapshot_datetime', 'host', 'comm', 'username'])[
            'cpu_norm'].sum().reset_index()  # Sum the norm diff by host and process at each sampling interval
        df_grouped = df_grouped[df_grouped['cpu_norm'] != 0]  # drops where the diff = 0
        if limit_to_host is not None:
            df_grouped = df_grouped[df_grouped['host'] == limit_to_host]

        return df_grouped


    def usage(self, df, host=None):
        df.dropna(inplace=True)
        if host is not None:
            df.drop(df[df.host != host].index, inplace=True)

        df_agg = df.groupby('snapshot_datetime'). \
            agg({'pid': 'count',
                 'cpu_norm': 'sum'}). \
            reset_index().sort_values(by='snapshot_datetime', ascending=True)

        return df_agg


    def top_load_command(self, df, limit_to_host=None):
        ## Feature engineering: identify the max CPU normalized difference at each sample time for each host

        top_command = self.common_group_load(df, limit_to_host).sort_values('cpu_norm').drop_duplicates(['snapshot_datetime',
                                                                                                    'host'],
                                                                                                   keep='last')  # Filter for max cpu diff and id the process command
        top_command.sort_values(by='snapshot_datetime', inplace=True)

        return top_command


    def top_memory_command(self, df, limit_to_host=None):
        ## Feature engineering: identify the max CPU normalized difference at each sample time for each host

        top_command = self.common_group_memory(df, limit_to_host).sort_values('rss').drop_duplicates(['snapshot_datetime',
                                                                                                 'host'],
                                                                                                keep='last')  # Filter for max cpu diff and id the process command
        top_command.sort_values(by='snapshot_datetime', inplace=True)

        return top_command


    def top_users_memory_commands(self, df, limit_to_host=None):
        df_max_0 = self.common_group_memory(df, limit_to_host).groupby(['snapshot_datetime', 'comm', 'host', 'username']).agg(
            {'rss': 'sum'}).reset_index()
        top_users_and_commands = df_max_0[df_max_0['rss'] > 2]

        return top_users_and_commands


    def top_users_load_commands(self, df, limit_to_host=None):
        df_max_0 = self.common_group_load(df, limit_to_host).groupby(['snapshot_datetime', 'comm', 'host', 'username']).agg(
            {'cpu_norm': 'sum'}).reset_index()
        top_users_and_commands = df_max_0[df_max_0['cpu_norm'] > 2]

        return top_users_and_commands


    def create_app(self):
        external_stylesheets = [dbc.themes.BOOTSTRAP, 'https://codepen.io/chriddyp/pen/bWLwgP.css']
        global server
        server = Flask(__name__)

        self.app = dash.Dash(__name__,
                        title='Load analyzer',
                        prevent_initial_callbacks=True,
                        external_stylesheets=external_stylesheets,
                        server=server)



    def sidebar_div(self,  df):
        server_array = df['host'].unique()
        dropdown = dcc.Dropdown(server_array, server_array[0], id='demo-dropdown')
        label = dash.html.Label("--------",
                                style={"margin-left": 0},
                                )
        container = html.Div(id='dd-output-container')

        @self.app.callback(
            Output('dd-output-container', 'children'),
            Input('demo-dropdown', 'value')
        )
        def update_output(value):
            return f'You have selected {value}'

        return dbc.Row(children=[dropdown, label, container])


    def page_content_div(self, df):
        # return (dbc.Row(id='page-content',
        #                 # style=MAIN_STYLE,
        #                 children=[load_graph_one_server(df, 'rosalindf',256),
        #                           load_graph_one_server(df, 'alice',192),
        #                           load_graph_one_server(df, 'tdobz',96),
        #                           memory_graph_one_server(df, 'rosalindf', 2000),
        #                           memory_graph_one_server(df, 'alice', 1000),
        #                           memory_graph_one_server(df, 'tdobz', 1000)
        #                           ]))

        return (dbc.Row(id='page-content',
                        # style=MAIN_STYLE,
                        children=[self.unified_graph_one_server(df, 'rosalindf', 256),
                                  self.unified_graph_one_server(df, 'alice', 192),
                                  self.unified_graph_one_server(df, 'tdobz', 96),
                                  ]))


    def memory_graph_one_server(self, df, hostname, mem_limit):
        top_memory_users_commands_df = self.top_users_memory_commands(df, hostname)

        top_memory_command_df = self.top_memory_command(df, hostname)

        fig = go.Figure()
        all_tuples = []

        for index, row in top_memory_command_df.iterrows():
            entry = ''
            cur_datetime = row['snapshot_datetime']
            tops = top_memory_users_commands_df[
                top_memory_users_commands_df['snapshot_datetime'] == cur_datetime].sort_values(
                by='rss', ascending=False)
            for sindex, srow in tops.iterrows():
                entry += f"<br>Host: {srow['host']} username: {srow['username']} load: {srow['rss']:.2f} command: {srow['comm']}"

            all_tuples.append(entry)

        customdata = np.stack(all_tuples, axis=-1)

        load_trace = go.Scatter(
            mode='lines',
            x=top_memory_command_df['snapshot_datetime'],
            y=top_memory_command_df['rss'],
            customdata=customdata,
            hovertemplate=('<br><b>Time:</b>: %{x}<br>' + \
                           '<i>Total memory</i>: %{y:.2f}' + \
                           '<br>%{customdata}'
                           ),
            line=dict(
                color="blue",
                width=1
            )
        )

        fig.add_trace(load_trace)
        fig.add_hline(y=mem_limit, line_color="red", line_dash="dash")

        fig.update_layout(title=f"Memory graph for {hostname}")

        graph = dcc.Graph(id=f'memory-graph-{hostname}', figure=fig)
        return graph


    def unified_graph_one_server(self, df, hostname, mem_limit):
        top_memory_users_commands_df = self.top_users_memory_commands(df, hostname)

        top_memory_command_df = self.top_memory_command(df, hostname)
        top_load_users_commands_df = self.top_users_load_commands(df, hostname)

        top_load_command_df = self.top_load_command(df, hostname)

        fig = go.Figure()
        all_tuples = []

        for index, row in top_memory_command_df.iterrows():
            entry = ''
            cur_datetime = row['snapshot_datetime']
            tops = top_memory_users_commands_df[
                top_memory_users_commands_df['snapshot_datetime'] == cur_datetime].sort_values(
                by='rss', ascending=False)
            for sindex, srow in tops.iterrows():
                entry += f"<br>Host: {srow['host']} username: {srow['username']} mem: {srow['rss']:.2f}G command: {srow['comm']}"

            all_tuples.append(entry)

        customdata = np.stack(all_tuples, axis=-1)

        memory_trace = go.Scatter(
            mode='lines',
            name="Memory",
            x=top_memory_command_df['snapshot_datetime'],
            y=top_memory_command_df['rss'],
            customdata=customdata,
            hovertemplate=('<br><b>Time:</b>: %{x}<br>' + \
                           '<i>Total memory</i>: %{y:.2f}G' + \
                           '<br>%{customdata}'
                           ),
            line=dict(
                color="red",
                width=1
            )
        )

        for index, row in top_load_command_df.iterrows():
            entry = ''
            cur_datetime = row['snapshot_datetime']
            tops = top_load_users_commands_df[top_load_users_commands_df['snapshot_datetime'] == cur_datetime].sort_values(
                by='cpu_norm', ascending=False)
            for sindex, srow in tops.iterrows():
                entry += f"<br>Host: {srow['host']} username: {srow['username']} load: {srow['cpu_norm']:.2f} command: {srow['comm']}"

            all_tuples.append(entry)

        customdata = np.stack(all_tuples, axis=-1)

        load_trace = go.Scatter(
            mode='lines',
            name="Load",
            x=top_load_command_df['snapshot_datetime'],
            y=top_load_command_df['cpu_norm'],
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

        fig.add_trace(load_trace)
        fig.add_trace(memory_trace)
        # fig.add_hline(y=mem_limit, line_color="red", line_dash="dash")

        fig.update_layout(title=f"unified graph for {hostname}")

        graph = dcc.Graph(id=f'unified-graph-{hostname}', figure=fig)
        return graph


    def load_graph_one_server(self, df, hostname, cpu_limit):
        top_load_users_commands_df = self.top_users_load_commands(df, hostname)

        top_load_command_df = self.top_load_command(df, hostname)

        fig = go.Figure()
        all_tuples = []

        for index, row in top_load_command_df.iterrows():
            entry = ''
            cur_datetime = row['snapshot_datetime']
            tops = top_load_users_commands_df[top_load_users_commands_df['snapshot_datetime'] == cur_datetime].sort_values(
                by='cpu_norm', ascending=False)
            for sindex, srow in tops.iterrows():
                entry += f"<br>Host: {srow['host']} username: {srow['username']} load: {srow['cpu_norm']:.2f} command: {srow['comm']}"

            all_tuples.append(entry)

        customdata = np.stack(all_tuples, axis=-1)

        load_trace = go.Scatter(
            mode='lines',
            x=top_load_command_df['snapshot_datetime'],
            y=top_load_command_df['cpu_norm'],
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

        fig.add_trace(load_trace)
        fig.add_hline(y=cpu_limit, line_color="red", line_dash="dash")

        fig.update_layout(title=f"Load graph for {hostname}")

        graph = dcc.Graph(id=f'load-graph-{hostname}', figure=fig)
        return graph


    def app_setup(self, df):
        self.create_app()
        TOPLEVEL_STYLE = {
            # "width": "160rem"

        }
        # start_date = df['snapshot_datetime_date'].min()
        # end_date = df['snapshot_datetime_date'].max()

        main_div = dbc.Row(children=[
            # dbc.Col(width=1,
            #         children=[
            #             dbc.Row(dash.html.Label("Material 1 as a sdas asd asd asd asd addsfdsfg asdf dfasd fadsf adsfgdsfg",
            #                                     style={"margin-left": 0},
            #                                     ))]),

            dbc.Col(width=1,
                    children=[dbc.Row([self.sidebar_div(df)])]),
            dbc.Col(width=11,
                    children=[dbc.Row(style={'overflow': 'auto',
                                             'overflow': 'visible'},
                                      children=[self.page_content_div(df)]
                                      )])
        ])

        self.app.layout = html.Div(
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


    def setup(self, use_tsv=True):
        PICKLE_FILE = './dataframe_pickle.pkl'
        if not os.path.exists(PICKLE_FILE):

            print("Creating a new pickle cache...")
            if use_tsv:
                df = self.read_tsv()
            else:
                df = self.read_sql()
            df = self.initial_data_wrangling(df)
            dbfile = open(PICKLE_FILE, 'ab')

            pickle.dump(df, dbfile)
            dbfile.close()
        else:
            dbfile = open(PICKLE_FILE, 'rb')
            df = pickle.load(dbfile)
            # print(df.shape, f"\n", df.dtypes)

        if self.app is None:
            self.app_setup(df)
            print("App is set up.")

analyer = Analyze()
if __name__ == '__main__':
    analyer.setup(False)
    print("Running internal server...")
    analyer.app.run_server(debug=True)
else:
    print(f"Running external server: {__name__}")
    analyer.setup()

print("exiting.")
