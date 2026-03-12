import Plot from 'react-plotly.js';
import { USER_COLORS } from '../config';

export default function UserStackedChart({ server, dataKey, valueLabel, yLimit }) {
  const chartData = server[dataKey];
  if (!chartData) return null;

  const { timestamps, users, series } = chartData;

  const traces = users.map((user, i) => ({
    x: timestamps,
    y: series[user],
    type: 'scatter',
    mode: 'lines',
    name: user,
    stackgroup: 'one',
    line: { color: USER_COLORS[i % USER_COLORS.length], width: 0 },
    hovertemplate: `<b>${user}</b>: %{y:.2f}<extra></extra>`,
  }));

  const layout = {
    title: `${valueLabel} by user on ${server.hostname}`,
    xaxis: { title: 'Time' },
    yaxis: { title: valueLabel, range: [0, yLimit] },
    uirevision: 'preserve UI state during updates',
    margin: { t: 40, b: 40, l: 60, r: 60 },
    height: 350,
    legend: { orientation: 'h', y: -0.2 },
  };

  return (
    <Plot
      data={traces}
      layout={layout}
      useResizeHandler
      style={{ width: '100%' }}
      config={{ responsive: true }}
    />
  );
}
