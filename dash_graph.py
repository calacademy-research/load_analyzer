import dash
import numpy as np
import plotly.express as px
from dash import dcc, html, Input, Output, callback, State, dash_table
from flask import Flask
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import datetime
import pandas as pd
from redis_transformer import RedisReader, timer
import logging
import json
import os
from zoneinfo import ZoneInfo

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

GPU_HOSTS = ['alice', 'ibss-spark-1']

SERVERS = [
    ('flor', 256, 1500),
    ('rosalindf', 256, 2000),
    ('alice', 192, 1000),
    ('tdobz', 96, 1000),
    ('ibss-spark-1', 20, 121),
]

# Color palette for per-user stacked area charts
USER_COLORS = px.colors.qualitative.Plotly + px.colors.qualitative.Set2 + px.colors.qualitative.Pastel

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

        self.app.layout = html.Div([
            dcc.Location(id='url', refresh=False),
            html.Div([
                dcc.DatePickerRange(
                    id='date-range',
                    start_date=None,
                    end_date=None,
                    display_format='YYYY-MM-DD',
                    minimum_nights=0
                ),
                html.Button('Update', id='submit-button', n_clicks=0, style={'margin-left': '10px'}),
            ], style={'margin': '10px'}),
            dcc.Tabs(id='tabs', value='overview', children=[
                dcc.Tab(label='Overview', value='overview', children=[
                    dcc.Loading(
                        id='loading-overview',
                        type='circle',
                        color='#119DFF',
                        children=[html.Div(id='graphs', children=self.create_graphs())],
                    ),
                ]),
                dcc.Tab(label='Per-User Breakdown', value='per-user', children=[
                    dcc.Loading(
                        id='loading-per-user',
                        type='circle',
                        color='#119DFF',
                        children=[
                            html.Div(id='top-consumers-table'),
                            html.Div(id='user-graphs'),
                        ],
                    ),
                ]),
            ]),
            dcc.Interval(
                id='interval-component',
                interval=120 * 1000,
                n_intervals=0,
            )
        ])

        @self.app.callback(
            [Output('date-range', 'start_date'),
             Output('date-range', 'end_date')],
            [Input('url', 'search')],
            prevent_initial_call=False
        )
        def initialize_dates(search):
            if search:
                try:
                    from urllib.parse import parse_qs
                    params = parse_qs(search.lstrip('?'))
                    start = params.get('start', [None])[0]
                    end = params.get('end', [None])[0]
                    if start and end:
                        return start, end
                except:
                    pass

            end_date = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles'))
            end_date = end_date.replace(tzinfo=datetime.timezone.utc)
            start_date = end_date - datetime.timedelta(days=1)
            logger.info(f"start_date: {start_date}, end_date: {end_date}")
            return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

        @self.app.callback(
            Output('url', 'search'),
            [Input('submit-button', 'n_clicks')],
            [State('date-range', 'start_date'),
             State('date-range', 'end_date')]
        )
        def update_url(n_clicks, start_date, end_date):
            if start_date and end_date:
                return f'?start={start_date}&end={end_date}'
            return ''

        @self.app.callback(
            Output('graphs', 'children'),
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
                if start_date is None:
                    start_datetime = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) - datetime.timedelta(days=1)
                else:
                    start_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d')
                if end_date is None:
                    end_datetime = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) + datetime.timedelta(days=1)
                else:
                    end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                # include the end date in the query
                end_datetime += datetime.timedelta(days=1)
                end_datetime = end_datetime.replace(tzinfo=datetime.timezone.utc)
                start_datetime = start_datetime.replace(tzinfo=datetime.timezone.utc)
                graphs = self.create_graphs(start_datetime, end_datetime)
                logger.debug(f"Created {len(graphs)} graphs")
                return graphs
            except Exception as e:
                logger.error(f"Error updating graphs: {str(e)}", exc_info=True)
                raise

        @self.app.callback(
            [Output('user-graphs', 'children'),
             Output('top-consumers-table', 'children')],
            [Input('submit-button', 'n_clicks'),
             Input('interval-component', 'n_intervals')],
            [State('date-range', 'start_date'),
             State('date-range', 'end_date')],
            prevent_initial_call=False
        )
        def update_user_graphs(n_clicks, n_intervals, start_date, end_date):
            try:
                if start_date is None:
                    start_datetime = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) - datetime.timedelta(days=1)
                else:
                    start_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d')
                if end_date is None:
                    end_datetime = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) + datetime.timedelta(days=1)
                else:
                    end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                end_datetime += datetime.timedelta(days=1)
                end_datetime = end_datetime.replace(tzinfo=datetime.timezone.utc)
                start_datetime = start_datetime.replace(tzinfo=datetime.timezone.utc)
                user_graphs, all_user_data = self.create_user_graphs(start_datetime, end_datetime)
                table = self.create_top_consumers_table(all_user_data)
                return user_graphs, table
            except Exception as e:
                logger.error(f"Error updating user graphs: {str(e)}", exc_info=True)
                raise

    @timer
    def create_graphs(self, start_date=None, end_date=None):
        if start_date is None:
            start_date = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) - datetime.timedelta(days=1)
            start_date = start_date.replace(tzinfo=datetime.timezone.utc)
        if end_date is None:
            end_date = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) + datetime.timedelta(days=1)
            end_date = end_date.replace(tzinfo=datetime.timezone.utc)
        return [
            self.unified_graph_one_server(host, cpu, mem, start_date, end_date)
            for host, cpu, mem in SERVERS
        ]

    def _create_hover_data(self, command_df, graph_data, data_type, value_field):
        """Helper function to create hover data for both memory and CPU load"""
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
    def _get_gpu_df(self, hostname, start_date, end_date):
        """Get GPU data as a DataFrame for a given host"""
        try:
            gpu_data = self.redis_reader.get_gpu_data(hostname, start_date, end_date)
            if not gpu_data:
                return pd.DataFrame()

            rows = []
            for timestamp, data in gpu_data.items():
                rows.append({
                    'snapshot_datetime': datetime.datetime.fromtimestamp(timestamp),
                    'utilization_pct': data.get('utilization_pct', 0),
                    'memory_used_mb': data.get('memory_used_mb', 0),
                    'memory_total_mb': data.get('memory_total_mb', 0),
                    'gpu_count': data.get('gpu_count', 0),
                    'gpu_processes': data.get('gpu_processes', ''),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            logger.error(f"Error getting GPU data for {hostname}: {e}")
            return pd.DataFrame()

    @timer
    def create_user_graphs(self, start_date=None, end_date=None):
        if start_date is None:
            start_date = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) - datetime.timedelta(days=1)
            start_date = start_date.replace(tzinfo=datetime.timezone.utc)
        if end_date is None:
            end_date = datetime.datetime.now(tz=ZoneInfo('America/Los_Angeles')) + datetime.timedelta(days=1)
            end_date = end_date.replace(tzinfo=datetime.timezone.utc)

        graphs = []
        all_user_data = []  # collect for the top consumers table

        for hostname, cpu_limit, mem_limit in SERVERS:
            graph_data = self.redis_reader.get_data(hostname, start_date, end_date)
            if not graph_data:
                continue

            cpu_user_df = self._convert_to_df(graph_data, 'cpu', 'user')
            mem_user_df = self._convert_to_df(graph_data, 'mem', 'user')

            # Collect for top consumers table
            if not cpu_user_df.empty:
                all_user_data.append(('cpu', hostname, cpu_user_df))
            if not mem_user_df.empty:
                all_user_data.append(('mem', hostname, mem_user_df))

            fig = make_subplots(rows=1, cols=2,
                                subplot_titles=[f'{hostname} — CPU by user', f'{hostname} — Memory by user'],
                                horizontal_spacing=0.08)

            # CPU stacked area (left)
            if not cpu_user_df.empty:
                cpu_by_user = cpu_user_df.groupby(['snapshot_datetime', 'username'])['cpu_norm'].sum().reset_index()
                users = cpu_by_user.groupby('username')['cpu_norm'].sum().sort_values(ascending=False)
                # Top 10 users, rest as "other"
                top_users = list(users.index[:10])
                if len(users) > 10:
                    cpu_by_user.loc[~cpu_by_user['username'].isin(top_users), 'username'] = 'other'
                    cpu_by_user = cpu_by_user.groupby(['snapshot_datetime', 'username'])['cpu_norm'].sum().reset_index()
                    top_users.append('other')

                for i, user in enumerate(top_users):
                    user_data = cpu_by_user[cpu_by_user['username'] == user].sort_values('snapshot_datetime')
                    fig.add_trace(go.Scatter(
                        x=user_data['snapshot_datetime'],
                        y=user_data['cpu_norm'],
                        mode='lines',
                        name=user,
                        stackgroup='cpu',
                        line=dict(color=USER_COLORS[i % len(USER_COLORS)], width=0),
                        fillcolor=USER_COLORS[i % len(USER_COLORS)],
                        hovertemplate=f'<b>{user}</b><br>CPU: %{{y:.1f}}<br>%{{x}}<extra></extra>',
                    ), row=1, col=1)

            # Memory stacked area (right)
            if not mem_user_df.empty:
                mem_by_user = mem_user_df.groupby(['snapshot_datetime', 'username'])['rss'].sum().reset_index()
                users = mem_by_user.groupby('username')['rss'].sum().sort_values(ascending=False)
                top_users = list(users.index[:10])
                if len(users) > 10:
                    mem_by_user.loc[~mem_by_user['username'].isin(top_users), 'username'] = 'other'
                    mem_by_user = mem_by_user.groupby(['snapshot_datetime', 'username'])['rss'].sum().reset_index()
                    top_users.append('other')

                for i, user in enumerate(top_users):
                    user_data = mem_by_user[mem_by_user['username'] == user].sort_values('snapshot_datetime')
                    fig.add_trace(go.Scatter(
                        x=user_data['snapshot_datetime'],
                        y=user_data['rss'],
                        mode='lines',
                        name=user,
                        stackgroup='mem',
                        showlegend=False,
                        line=dict(color=USER_COLORS[i % len(USER_COLORS)], width=0),
                        fillcolor=USER_COLORS[i % len(USER_COLORS)],
                        hovertemplate=f'<b>{user}</b><br>Memory: %{{y:.1f}}G<br>%{{x}}<extra></extra>',
                    ), row=1, col=2)

            fig.update_yaxes(title_text='CPU load', range=[0, cpu_limit], row=1, col=1)
            fig.update_yaxes(title_text='Memory (GB)', range=[0, mem_limit], row=1, col=2)
            fig.update_layout(height=400, uirevision='preserve UI state during updates')

            graphs.append(dcc.Graph(id=f'user-graph-{hostname}', figure=fig))

        return graphs, all_user_data

    @timer
    def create_top_consumers_table(self, all_user_data):
        if not all_user_data:
            return html.P("No user data available for the selected period.")

        rows = []
        for data_type, hostname, df in all_user_data:
            if data_type == 'cpu':
                by_user = df.groupby('username').agg(
                    avg_load=('cpu_norm', 'mean'),
                    peak_load=('cpu_norm', 'max'),
                    samples=('cpu_norm', 'count'),
                ).reset_index()
                for _, row in by_user.iterrows():
                    rows.append({
                        'Server': hostname,
                        'User': row['username'],
                        'Avg CPU Load': round(row['avg_load'], 1),
                        'Peak CPU Load': round(row['peak_load'], 1),
                        'Avg Memory (GB)': '',
                        'Peak Memory (GB)': '',
                    })
            elif data_type == 'mem':
                by_user = df.groupby('username').agg(
                    avg_mem=('rss', 'mean'),
                    peak_mem=('rss', 'max'),
                ).reset_index()
                for _, row in by_user.iterrows():
                    # Find existing row for this user/server and merge
                    existing = [r for r in rows if r['Server'] == hostname and r['User'] == row['username']]
                    if existing:
                        existing[0]['Avg Memory (GB)'] = round(row['avg_mem'], 1)
                        existing[0]['Peak Memory (GB)'] = round(row['peak_mem'], 1)
                    else:
                        rows.append({
                            'Server': hostname,
                            'User': row['username'],
                            'Avg CPU Load': '',
                            'Peak CPU Load': '',
                            'Avg Memory (GB)': round(row['avg_mem'], 1),
                            'Peak Memory (GB)': round(row['peak_mem'], 1),
                        })

        if not rows:
            return html.P("No user data available for the selected period.")

        table_df = pd.DataFrame(rows)
        # Sort by peak CPU load descending (treat empty as 0)
        table_df['_sort'] = pd.to_numeric(table_df['Peak CPU Load'], errors='coerce').fillna(0)
        table_df = table_df.sort_values('_sort', ascending=False).drop('_sort', axis=1)

        return html.Div([
            html.H3("Top Consumers", style={'margin': '10px'}),
            dash_table.DataTable(
                id='consumers-datatable',
                columns=[{'name': c, 'id': c} for c in table_df.columns],
                data=table_df.to_dict('records'),
                sort_action='native',
                filter_action='native',
                page_size=20,
                style_table={'overflowX': 'auto', 'margin': '10px'},
                style_cell={'textAlign': 'left', 'padding': '8px'},
                style_header={'fontWeight': 'bold', 'backgroundColor': '#f0f0f0'},
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': '#fafafa'},
                ],
            ),
        ])

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
            if not top_memory_command_df.empty:
                logger.debug(f"Creating memory trace for {hostname}")
                # Cap RSS at mem_limit so the line stays visible on the chart
                top_memory_command_df = top_memory_command_df.copy()
                top_memory_command_df['rss_display'] = top_memory_command_df['rss'].clip(upper=mem_limit)
                if len(mem_hover_data) > 0:
                    top_memory_command_df['hover_data'] = mem_hover_data
                    custom_data_cols = ['hover_data', 'rss']
                    hover_tpl = ('<br><b>Time:</b>: %{x}<br>'
                                 '<i>Total memory</i>: %{customdata[1]:.2f}G'
                                 '<br>%{customdata[0]}')
                else:
                    top_memory_command_df['hover_data'] = ''
                    custom_data_cols = ['hover_data', 'rss']
                    hover_tpl = ('<br><b>Time:</b>: %{x}<br>'
                                 '<i>Total memory</i>: %{customdata[1]:.2f}G')
                memory_trace = px.line(
                    top_memory_command_df,
                    x='snapshot_datetime',
                    y='rss_display',
                    custom_data=custom_data_cols,
                    color_discrete_sequence=['red'],
                    labels={'snapshot_datetime': 'Time', 'rss_display': 'Total memory (GB)', 'comm': 'command'},
                    title=f"CPU and memory usage on {hostname}")
                memory_trace.update_traces(
                    hovertemplate=hover_tpl,
                    line=dict(width=3),
                    opacity=0.7,
                    yaxis='y2'  # Use secondary y-axis for memory
                )
                fig.add_trace(memory_trace.data[0], secondary_y=True)
                logger.debug("Memory trace created successfully")

            if not top_load_command_df.empty:
                logger.debug(f"Creating CPU load trace for {hostname}")
                top_load_command_df = top_load_command_df.copy()
                if len(load_hover_data) > 0:
                    top_load_command_df['hover_data'] = load_hover_data
                    custom_data_cols = ['hover_data']
                    hover_tpl = ('<br><b>Time:</b>: %{x}<br>'
                                 '<i>Total load</i>: %{y:.2f}'
                                 '<br>%{customdata[0]}')
                else:
                    top_load_command_df['hover_data'] = ''
                    custom_data_cols = ['hover_data']
                    hover_tpl = ('<br><b>Time:</b>: %{x}<br>'
                                 '<i>Total load</i>: %{y:.2f}')
                load_trace = px.line(
                    top_load_command_df,
                    x='snapshot_datetime',
                    y='cpu_norm',
                    custom_data=custom_data_cols,
                    color_discrete_sequence=['blue'],
                    labels={'snapshot_datetime': 'Time', 'cpu_norm': 'Total load', 'comm': 'command'},
                    title=f"CPU and memory usage on {hostname}"
                )

                load_trace.update_traces(
                    hovertemplate=hover_tpl,
                    line=dict(width=2),
                    opacity=1,
                    yaxis='y1'  # Use primary y-axis for CPU
                )
                fig.add_trace(load_trace.data[0], secondary_y=False)
                logger.debug("CPU load trace created successfully")

            # Add GPU utilization trace (green) for GPU-equipped hosts
            if hostname in GPU_HOSTS:
                gpu_df = self._get_gpu_df(hostname, start_date, end_date)
                if not gpu_df.empty:
                    logger.debug(f"Creating GPU trace for {hostname}: {len(gpu_df)} points")
                    gpu_count = gpu_df['gpu_count'].max()
                    # Scale GPU % (0-100) to CPU axis range (0-cpu_limit)
                    gpu_scaled = gpu_df['utilization_pct'] * cpu_limit / 100.0
                    # Build customdata as list of lists to support mixed types (numeric + string)
                    custom = list(zip(
                        gpu_df['memory_used_mb'].values,
                        gpu_df['memory_total_mb'].values,
                        gpu_df['gpu_count'].values,
                        gpu_df['utilization_pct'].values,
                        gpu_df['gpu_processes'].fillna('').values,
                    ))
                    gpu_trace = go.Scatter(
                        x=gpu_df['snapshot_datetime'],
                        y=gpu_scaled,
                        mode='lines',
                        name='GPU utilization %',showlegend=False,
                        line=dict(color='green', width=2),
                        opacity=0.9,
                        hovertemplate=(
                            '<br><b>Time:</b> %{x}<br>'
                            '<i>GPU utilization</i>: %{customdata[3]:.1f}%'
                            '<br>Memory: %{customdata[0]:.0f} / %{customdata[1]:.0f} MB'
                            '<br>GPUs: %{customdata[2]}'
                            '<br>%{customdata[4]}'
                        ),
                        customdata=custom,
                    )
                    fig.add_trace(gpu_trace, secondary_y=False)
                    logger.debug("GPU trace created successfully")
                else:
                    logger.debug(f"No GPU data available for {hostname}")

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
    # When running directly for development, use port 8050
    graphs.app.run(debug=True, host='0.0.0.0', port=80, use_reloader=False)
else:
    # When running through Apache/WSGI, just expose the server
    print(f"Running through WSGI: {__name__}")

print("exiting.")
