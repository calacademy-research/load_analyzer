import dash
import dash_bootstrap_components as dbc
import numpy as np
import plotly.graph_objects as go
from dash import dcc, html, Input, Output, callback
from flask import Flask
from plotly.subplots import make_subplots

from analyze import Analyze

server = None


class DashGraph:
    df = None
    app = None
    analyze = None
    server = None

    def __init__(self, analyze):
        self.analyze = analyze

        if self.app is None:
            self.app_setup()
            print("App is set up.")

    def app_setup(self):
        external_stylesheets = [dbc.themes.BOOTSTRAP, 'https://codepen.io/chriddyp/pen/bWLwgP.css']
        @callback(Output('graphs', 'children'),
                  Input('interval-component', 'n_intervals'))
        def update_graphs(intervals):
            analyzer.update_df()
            return self.create_graphs()

        self.server = Flask(__name__)
        self.app = dash.Dash(__name__,
                             title='Load analyzer',
                             external_stylesheets=external_stylesheets,
                             prevent_initial_callbacks=True,
                             server=self.server)
        self.app.layout = self.get_layout

    def get_layout(self):
        return html.Div(
            children=[
                html.Div(id='graphs', children=self.create_graphs()),
                dcc.Interval(
                    id='interval-component',
                    interval=120 * 1000,  # 30 seconds total
                    n_intervals=0,
                )
            ]
        )

    def create_graphs(self):
        return [
            self.unified_graph_one_server('flor', 256, 1500),
            self.unified_graph_one_server('rosalindf', 256, 2000),
            self.unified_graph_one_server('alice', 192, 1000),
            self.unified_graph_one_server('tdobz', 96, 1000)
        ]

    def unified_graph_one_server(self, hostname, cpu_limit, mem_limit):
        top_memory_users_commands_df = self.analyze.top_users_memory_commands(hostname)

        top_memory_command_df = self.analyze.top_memory_command(hostname)
        top_load_users_commands_df = self.analyze.top_users_load_commands(hostname)

        top_load_command_df = self.analyze.top_load_command(hostname)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
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

analyzer = Analyze(use_tsv=False, use_pickle=False)
graphs = DashGraph(analyzer)
server = graphs.server
if __name__ == '__main__':
    print("Running internal server...")
    graphs.app.run_server(debug=True, host='127.0.0.1', use_reloader=False)
else:
    print(f"Running external server: {__name__}")

print("exiting.")
