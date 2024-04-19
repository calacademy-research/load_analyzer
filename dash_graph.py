import dash
import plotly.express as px
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
        @callback(
            [Output('graphs', 'children'),
            Output('loading', 'parent_style')],
            Input('interval-component', 'n_intervals')
        )
        def update_graphs(_):
            analyzer.update_df()
            return self.create_graphs(), {'display' : 'none'}

        self.server = Flask(__name__)
        self.app = dash.Dash(__name__,
                             title='Load analyzer',
                             prevent_initial_callbacks=True,
                             server=self.server)
        self.app.layout = self.get_layout

    def get_layout(self):
        return html.Div(
            children=[
                dcc.Loading(
                    id='loading',
                    type='graph',
                    fullscreen=True
                ),
                html.Div(id='graphs', children=self.create_graphs()),
                dcc.Interval(
                    id='interval-component',
                    interval=120 * 1000,
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
        top_memory_command_df = self.analyze.top_memory_command(hostname)
        top_load_command_df = self.analyze.top_load_command(hostname)
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        memory_trace = px.line(
            top_memory_command_df,
            x='snapshot_datetime',
            y='rss',
            hover_data={'snapshot_datetime': True, 'rss': ':.2f', 'host': True, 'username': True, 'comm': True},
            color_discrete_sequence=['red'],
            labels={'snapshot_datetime': 'Time', 'rss': 'Total memory (GB)', 'comm': 'command'},
            title=f"CPU and memory usage on {hostname}")

        load_trace = px.line(
            top_load_command_df,
            x='snapshot_datetime',
            y='cpu_norm',
            hover_data={'snapshot_datetime': True, 'cpu_norm': ':.2f', 'host': True, 'username': True, 'comm': True},
            color_discrete_sequence=['blue'],
            labels={'snapshot_datetime': 'Time', 'cpu_norm': 'Total load', 'comm': 'command'},
            title=f"CPU and memory usage on {hostname}"
        )

        fig.add_trace(load_trace.data[0])
        fig.add_trace(memory_trace.data[0], secondary_y=True)

        fig.update_yaxes(range=[0, mem_limit], secondary_y=True, title="Memory usage")
        fig.update_yaxes(range=[0, cpu_limit], secondary_y=False, title="CPU usage")
        fig.update_layout(title=f"CPU and memory usage on {hostname}")

        return dcc.Graph(id=f'unified-graph-{hostname}', figure=fig)

analyzer = Analyze(use_tsv=False, use_pickle=False)
graphs = DashGraph(analyzer)
server = graphs.server
if __name__ == '__main__':
    print("Running internal server...")
    graphs.app.run_server(debug=True, host='127.0.0.1', use_reloader=False)
else:
    print(f"Running external server: {__name__}")

print("exiting.")
