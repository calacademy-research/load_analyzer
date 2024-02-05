import plotly.express as px
from dash import Dash, dcc, html, Input, Output
import dash
from flask import Flask
import dash_html_components as html
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import numpy as np
from plotly.subplots import make_subplots

from analyze import Analyze

server = None


class DashGraph():
    df = None
    app = None
    analyze = None
    server = None

    def __init__(self, analyze):
        self.analyze = analyze

        if self.app is None:
            self.app_setup()
            print("App is set up.")

    # Arguments are 'comm' for by-command and 'username' (default) for by-user
    # Not used; may delete?
    def show_percent_usage_by(self, by="username"):
        # ** drop rows where username == args == pid == host and
        # retain the record with the highest cpu time.

        # Sort so that we choose only the highest value (i.e. final)
        # cputime. Cputime is cumulative (inherent in the output of linux)
        df_max_process_usage_only = self.analyze.df.sort_values('cputimes', ascending=False). \
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

    def create_app(self):
        external_stylesheets = [dbc.themes.BOOTSTRAP, 'https://codepen.io/chriddyp/pen/bWLwgP.css']
        self.server = Flask(__name__)

        self.app = dash.Dash(__name__,
                             title='Load analyzer',
                             prevent_initial_callbacks=True,
                             external_stylesheets=external_stylesheets,
                             server=self.server)

    def sidebar_div(self):
        server_array = self.analyze.df['host'].unique()
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

    def page_content_div(self):
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
                        children=[self.unified_graph_one_server('rosalindf', 256, 2000),
                                  self.unified_graph_one_server('alice', 192, 1000),
                                  self.unified_graph_one_server('tdobz', 96, 1000),
                                  ]))

    def unified_graph_one_server(self, hostname, cpu_limit, mem_limit):
        top_memory_users_commands_df = self.analyze.top_users_memory_commands(hostname)

        top_memory_command_df = self.analyze.top_memory_command(hostname)
        top_load_users_commands_df = self.analyze.top_users_load_commands(hostname)

        top_load_command_df = self.analyze.top_load_command(hostname)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        # fig = go.Figure()
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
        all_tuples=[]
        for index, row in top_load_command_df.iterrows():
            entry = ''
            cur_datetime = row['snapshot_datetime']
            tops = top_load_users_commands_df[
                top_load_users_commands_df['snapshot_datetime'] == cur_datetime].sort_values(
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
        fig.add_trace(memory_trace, secondary_y=True)
        fig.update_yaxes(range=[0, mem_limit], secondary_y=True, title="Memory usage")
        fig.update_yaxes(range=[0, cpu_limit], secondary_y=False, title="CPU usage")

        # fig.add_hline(y=mem_limit, line_color="red", line_dash="dash")

        fig.update_layout(title=f"CPU and memory usage on {hostname}")

        graph = dcc.Graph(id=f'unified-graph-{hostname}', figure=fig)
        return graph

    def load_graph_one_server(self, df, hostname, cpu_limit):
        top_load_users_commands_df = self.analyze.top_users_load_commands(df, hostname)

        top_load_command_df = self.analyze.top_load_command(df, hostname)

        fig = go.Figure()
        all_tuples = []

        for index, row in top_load_command_df.iterrows():
            entry = ''
            cur_datetime = row['snapshot_datetime']
            tops = top_load_users_commands_df[
                top_load_users_commands_df['snapshot_datetime'] == cur_datetime].sort_values(
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

    def app_setup(self):
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

            # dbc.Col(width=1,
            #         children=[dbc.Row([self.sidebar_div()])]),
            dbc.Col(width=12,
                    children=[dbc.Row(style={'overflow': 'auto',
                                             'overflow': 'visible'},
                                      children=[self.page_content_div()]
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


analyer = Analyze(use_tsv=False, use_pickle=False)
graphs = DashGraph(analyer)
server = graphs.server
if __name__ == '__main__':
    print("Running internal server...")
    graphs.app.run_server(debug=True, host='127.0.0.1',use_reloader=False)
else:
    print(f"Running external server: {__name__}")

print("exiting.")
