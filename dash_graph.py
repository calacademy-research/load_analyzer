import dash
import numpy as np
import plotly.express as px
from dash import dcc, html, Input, Output, callback, State
from flask import Flask
from plotly.subplots import make_subplots
import datetime
import pandas as pd
from redis_transformer import RedisReader, timer
import logging
import json
import os

# Create logs directory if it doesn't exist
os.makedirs('/var/log/dash_app', exist_ok=True)

# Set up logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # File handler
        logging.FileHandler('/var/log/dash_app/dash_app.log'),
        # Console handler
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
        
        # Add debug configurations
        self.app.enable_dev_tools(
            debug=True,
            dev_tools_hot_reload=True,
            dev_tools_props_check=True,
            dev_tools_serve_dev_bundles=True
        )

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
            logger.debug(f"Updating graphs: clicks={n_clicks}, intervals={n_intervals}")
            logger.debug(f"Date range: {start_date} to {end_date}")
            
            try:
                start_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d')
                end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d') + datetime.timedelta(days=1)
                graphs = self.create_graphs(start_datetime, end_datetime)
                logger.debug(f"Created {len(graphs)} graphs")
                return graphs, {'display': 'block'}
            except Exception as e:
                logger.error(f"Error updating graphs: {str(e)}", exc_info=True)
                raise

    @timer
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

    def _create_hover_data(self, command_df, graph_data, data_type, value_field):
        """Helper function to create hover data for both memory and CPU load
        
        Args:
            command_df: DataFrame with command data
            graph_data: Raw graph data
            data_type: Type of data ('mem' or 'cpu')
            value_field: Field to sort by ('rss' or 'cpu_norm')
        """
        users_df = self._convert_to_df(graph_data, data_type, 'user')
        if users_df.empty:
            return []

        # Pre-sort the dataframe once
        users_df = users_df.sort_values(['snapshot_datetime', value_field], ascending=[True, False])
        
        # Create a dictionary for faster lookups
        grouped_users = dict(list(users_df.groupby('snapshot_datetime')))
        
        # Use list comprehension instead of loop with append
        value_label = 'mem' if data_type == 'mem' else 'load'
        unit = 'G' if data_type == 'mem' else ''
        all_tuples = [
            "".join(
                f"<br>Host: {row['host']} username: {row['username']} {value_label}: {row[value_field]:.2f}{unit} command: {row['comm']}"
                for _, row in grouped_users.get(timestamp, pd.DataFrame()).iterrows()
            )
            for timestamp in command_df['snapshot_datetime']
        ]

        return np.array(all_tuples)

    @timer
    def memory_hover_data(self, top_memory_command_df, graph_data):
        return self._create_hover_data(top_memory_command_df, graph_data, 'mem', 'rss')

    @timer
    def load_hover_data(self, top_load_command_df, graph_data):
        return self._create_hover_data(top_load_command_df, graph_data, 'cpu', 'cpu_norm')

    @timer
    def _convert_to_df(self, data_dict, data_type, data_key):
        logger.debug(f"Converting data: type={data_type}, key={data_key}")
        df_dict = {}
        try:
            for key, value in data_dict.items():
                entry_data = value.get(data_type, {}).get(data_key, {})
                if not entry_data:
                    logger.debug(f"No data found for {data_type}/{data_key}")
                    continue
                if type(entry_data) == dict:
                    entry_data = [entry_data]
                for entry in entry_data:
                    if entry:
                        df_dict.setdefault('snapshot_datetime', []).append(datetime.datetime.fromtimestamp(key))
                        for entry_key, entry_value in entry.items():
                            df_dict.setdefault(entry_key, []).append(entry_value)
            
            if 'snapshot_datetime' in df_dict:
                logger.debug(f"Created DataFrame with {len(df_dict['snapshot_datetime'])} rows")
            else:
                logger.warning("No data points found for DataFrame creation")
            
            return pd.DataFrame(df_dict)
        except Exception as e:
            logger.error(f"Error converting data to DataFrame: {str(e)}", exc_info=True)
            return pd.DataFrame()

    @timer
    def unified_graph_one_server(self, hostname, cpu_limit, mem_limit, start_date=None, end_date=None):
        logger.debug(f"Fetching Redis data for {hostname} from {start_date} to {end_date}")
        graph_data = self.redis_reader.get_data(hostname, start_date, end_date)
        
        # Debug Redis data structure
        if graph_data:
            logger.debug(f"Redis data keys: {list(graph_data.keys())[:5]}...")
            sample_entry = next(iter(graph_data.values()))
            logger.debug(f"Sample data structure: {json.dumps(sample_entry, indent=2)}")
        
        top_memory_command_df = self._convert_to_df(graph_data, 'mem', 'command')
        logger.debug(f"Memory command data: {len(top_memory_command_df) if not top_memory_command_df.empty else 0} rows")
        mem_hover_data = self.memory_hover_data(top_memory_command_df, graph_data)
        
        top_load_command_df = self._convert_to_df(graph_data, 'cpu', 'command')
        logger.debug(f"CPU command data: {len(top_load_command_df) if not top_load_command_df.empty else 0} rows")
        load_hover_data = self.load_hover_data(top_load_command_df, graph_data)

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Add debug checks for empty data
        if len(mem_hover_data) == 0:
            logger.warning(f"No memory data available for {hostname}")
        if len(load_hover_data) == 0:
            logger.warning(f"No CPU load data available for {hostname}")

        # Debug trace creation
        try:
            if len(mem_hover_data) > 0:
                logger.debug(f"Creating memory trace for {hostname}")
                top_memory_command_df['hover_data'] = mem_hover_data
                # Slightly elevate memory values to avoid exact overlap
                top_memory_command_df['inflated_rss'] = top_memory_command_df['rss'] + 100.0
                memory_trace = px.line(
                    top_memory_command_df,
                    x='snapshot_datetime',
                    y='inflated_rss',
                    custom_data=['hover_data', 'rss'],
                    color_discrete_sequence=['red'],
                    labels={'snapshot_datetime': 'Time', 'rss': 'Total memory (GB)', 'comm': 'command'},
                    title=f"CPU and memory usage on {hostname}")
                memory_trace.update_traces(
                    hovertemplate=('<br><b>Time:</b>: %{x}<br>' + \
                                   '<i>Total memory</i>: %{customdata[1]:.2f}G' + \
                                   '<br>%{customdata[0]}'
                                   ),
                    line=dict(width=3),
                    opacity=0.7,
                    yaxis='y2'  # Use secondary y-axis for memory
                )
                fig.add_trace(memory_trace.data[0], secondary_y=True)
                logger.debug("Memory trace created successfully")
            
            if len(load_hover_data) > 0:
                logger.debug(f"Creating CPU load trace for {hostname}")
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
                                   '<br>%{customdata[0]}'),
                    line=dict(width=2),
                    opacity=1,
                    yaxis='y1'  # Use primary y-axis for CPU
                )
                fig.add_trace(load_trace.data[0], secondary_y=False)
                logger.debug("CPU load trace created successfully")
        except Exception as e:
            logger.error(f"Error creating traces for {hostname}: {str(e)}", exc_info=True)

        fig.update_yaxes(range=[0, mem_limit], secondary_y=True, title="Memory usage")
        fig.update_yaxes(range=[0, cpu_limit], secondary_y=False, title="CPU usage")
        fig.update_layout(title=f"CPU and memory usage on {hostname}")
        fig.update_layout(uirevision='preserve UI state during updates')

        return dcc.Graph(id=f'unified-graph-{hostname}', figure=fig)

graphs = DashGraph()
server = graphs.server
if __name__ == '__main__':
    print("Running internal server...")
    graphs.app.run_server(debug=True, host='127.0.0.1', port=80, use_reloader=False)
else:
    print(f"Running external server: {__name__}")

print("exiting.")
