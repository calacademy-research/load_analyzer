import dash
import numpy as np
import plotly.express as px
from dash import dcc, html, Input, Output, callback, State
from flask import Flask
from plotly.subplots import make_subplots
import datetime
import pandas as pd
from redis_transformer import RedisReader
server = None

class DashGraph:
    app = None
    server = None

    def __init__(self):
        self.redis_reader = RedisReader()
        if self.app is None:
            self.app_setup()
            print("App is set up.")

    def app_setup(self):
        self.server = Flask(__name__)
        self.app = dash.Dash(__name__,
                            title='Load analyzer',
                            prevent_initial_callbacks=True,
                            server=self.server)

        self.default_end_date = datetime.datetime.now()
        self.default_start_date = self.default_end_date - datetime.timedelta(days=1)

        self.app.layout = html.Div(
            children=[
                html.Div([
                    dcc.DatePickerRange(
                        id='date-range',
                        start_date=self.default_start_date.strftime('%Y-%m-%d'),
                        end_date=self.default_end_date.strftime('%Y-%m-%d'),
                        display_format='YYYY-MM-DD',
                        minimum_nights=0
                    ),
                    html.Button('Update', id='submit-button', n_clicks=0, style={'margin-left': '10px'}),
                ], style={'margin': '10px'}),
                dcc.Loading(
                    id='loading',
                    type='circle',
                    fullscreen=True,
                    color='#119DFF',
                ),
                html.Div(id='graphs', children=self.create_graphs()),
                dcc.Interval(
                    id='interval-component',
                    interval=120 * 1000,
                    n_intervals=0,
                )
            ]
        )

        @self.app.callback(
            [Output('graphs', 'children'),
             Output('loading', 'parent_style')],
            [Input('submit-button', 'n_clicks'),
             Input('interval-component', 'n_intervals')],
            [State('date-range', 'start_date'),
             State('date-range', 'end_date')],
            prevent_initial_call=False
        )
        def update_graphs(n_clicks, n_intervals, start_date, end_date):
            start_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d') + datetime.timedelta(days=1)
            return self.create_graphs(start_datetime, end_datetime), {'display': 'block'}

    def create_graphs(self, start_date=None, end_date=None):
        if start_date is None:
            start_date = self.default_start_date
        if end_date is None:
            end_date = self.default_end_date
        return [
            self.unified_graph_one_server('flor', 256, 1500, start_date, end_date),
            self.unified_graph_one_server('rosalindf', 256, 2000, start_date, end_date),
            self.unified_graph_one_server('alice', 192, 1000, start_date, end_date),
            self.unified_graph_one_server('tdobz', 96, 1000, start_date, end_date)
        ]

    def memory_hover_data(self, top_memory_command_df, graph_data):
        all_tuples = []
        top_memory_users = self._convert_to_df(graph_data, 'mem', 'user')
        if top_memory_users.empty:
            return []
        for index, row in top_memory_command_df.iterrows():
            entry = ''
            cur_datetime = row['snapshot_datetime']
            tops = top_memory_users[
                top_memory_users['snapshot_datetime'] == cur_datetime].sort_values(
                by='rss', ascending=False)
            for sindex, srow in tops.iterrows():
                entry += f"<br>Host: {srow['host']} username: {srow['username']} mem: {srow['rss']:.2f}G command: {srow['comm']}"

            all_tuples.append(entry)

        return np.stack(all_tuples, axis=-1)

    def load_hover_data(self, top_load_command_df, graph_data):
        all_tuples = []
        top_load_users = self._convert_to_df(graph_data, 'cpu', 'user')
        if top_load_users.empty:
            return []
        for index, row in top_load_command_df.iterrows():
            entry = ''
            cur_datetime = row['snapshot_datetime']
            tops = top_load_users[
                top_load_users['snapshot_datetime'] == cur_datetime].sort_values(
                by='cpu_norm', ascending=False)
            for sindex, srow in tops.iterrows():
                entry += f"<br>Host: {srow['host']} username: {srow['username']} load: {srow['cpu_norm']:.2f} command: {srow['comm']}"

            all_tuples.append(entry)

        return np.stack(all_tuples, axis=-1)

    def _convert_to_df(self, data_dict, data_type, data_key):
        df_dict = {}
        for key, value in data_dict.items():
            entry_data = value.get(data_type, {}).get(data_key, {})
            if not entry_data:
                return pd.DataFrame()
            if type(entry_data) == dict:
                entry_data = [entry_data]
            for entry in entry_data:
                df_dict.setdefault('snapshot_datetime', []).append(datetime.datetime.fromtimestamp(key))
                for entry_key, entry_value in entry.items():
                    df_dict.setdefault(entry_key, []).append(entry_value)
        if 'snapshot_datetime' in df_dict:
            df_dict['snapshot_datetime'] = pd.to_datetime(df_dict['snapshot_datetime'])
        return pd.DataFrame(df_dict)

    def unified_graph_one_server(self, hostname, cpu_limit, mem_limit, start_date=None, end_date=None):
        graph_data = self.redis_reader.get_data(hostname, start_date, end_date)
        top_memory_command_df = None #self._convert_to_df(graph_data, 'mem', 'command')
        mem_hover_data = [] #self.memory_hover_data(top_memory_command_df, graph_data)

        top_load_command_df = self._convert_to_df(graph_data, 'cpu', 'command')
        load_hover_data = self.load_hover_data(top_load_command_df, graph_data)
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Check if memory_hover_data is empty
        if len(mem_hover_data) > 0:
            top_memory_command_df['hover_data'] = mem_hover_data
            memory_trace = px.line(
                top_memory_command_df,
                x='snapshot_datetime',
                y='rss',
                custom_data=['hover_data'],
                color_discrete_sequence=['red'],
                labels={'snapshot_datetime': 'Time', 'rss': 'Total memory (GB)', 'comm': 'command'},
                title=f"CPU and memory usage on {hostname}")

            memory_trace.update_traces(
                hovertemplate=('<br><b>Time:</b>: %{x}<br>' + \
                               '<i>Total memory</i>: %{y:.2f}G' + \
                               '<br>%{customdata[0]}'
                               )
            )
            fig.add_trace(memory_trace.data[0], secondary_y=True)

        # Check if load_hover_data is empty
        if len(load_hover_data) > 0:
            top_load_command_df['hover_data'] = load_hover_data
            load_trace = px.line(
                top_load_command_df,
                x='snapshot_datetime',
                y='cpu_norm',
                custom_data=['hover_data'],
                color_discrete_sequence=['blue'],
                labels={'snapshot_datetime': 'Time', 'cpu_norm': 'Total load', 'comm': 'command'},
                title=f"CPU and memory usage on {hostname}"
            )

            load_trace.update_traces(
                hovertemplate=('<br><b>Time:</b>: %{x}<br>' + \
                               '<i>Total load</i>: %{y:.2f}' + \
                               '<br>%{customdata[0]}')
            )
            fig.add_trace(load_trace.data[0])

        fig.update_yaxes(range=[0, mem_limit], secondary_y=True, title="Memory usage")
        fig.update_yaxes(range=[0, cpu_limit], secondary_y=False, title="CPU usage")
        fig.update_layout(title=f"CPU and memory usage on {hostname}")
        fig.update_layout(uirevision='preserve UI state during updates')

        return dcc.Graph(id=f'unified-graph-{hostname}', figure=fig)

graphs = DashGraph()
server = graphs.server
if __name__ == '__main__':
    print("Running internal server...")
    graphs.app.run_server(debug=True, host='127.0.0.1', port=8090, use_reloader=False)
else:
    print(f"Running external server: {__name__}")

print("exiting.")
