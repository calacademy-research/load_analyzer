import Plot from 'react-plotly.js';

export default function ServerChart({ server }) {
  const { hostname, cpu_limit, mem_limit, cpu, mem, gpu } = server;
  const traces = [];

  // Memory trace (red, secondary y-axis)
  if (mem) {
    const customdata = mem.hover.length > 0
      ? mem.timestamps.map((_, i) => [
          (mem.hover[i] || []).join('<br>'),
          mem.raw_values[i],
        ])
      : mem.timestamps.map((_, i) => ['', mem.raw_values[i]]);

    const hovertemplate = mem.hover.length > 0
      ? '<br><b>Time:</b>: %{x}<br><i>Total memory</i>: %{customdata[1]:.2f}G<br>%{customdata[0]}'
      : '<br><b>Time:</b>: %{x}<br><i>Total memory</i>: %{customdata[1]:.2f}G';

    traces.push({
      x: mem.timestamps,
      y: mem.values,
      customdata,
      type: 'scatter',
      mode: 'lines',
      name: 'Memory',
      yaxis: 'y2',
      line: { color: 'red', width: 3 },
      opacity: 0.7,
      hovertemplate,
      showlegend: false,
    });
  }

  // CPU trace (blue, primary y-axis)
  if (cpu) {
    const customdata = cpu.hover.length > 0
      ? cpu.timestamps.map((_, i) => [(cpu.hover[i] || []).join('<br>')])
      : cpu.timestamps.map(() => ['']);

    const hovertemplate = cpu.hover.length > 0
      ? '<br><b>Time:</b>: %{x}<br><i>Total load</i>: %{y:.2f}<br>%{customdata[0]}'
      : '<br><b>Time:</b>: %{x}<br><i>Total load</i>: %{y:.2f}';

    traces.push({
      x: cpu.timestamps,
      y: cpu.values,
      customdata,
      type: 'scatter',
      mode: 'lines',
      name: 'CPU',
      yaxis: 'y',
      line: { color: 'blue', width: 2 },
      opacity: 1,
      hovertemplate,
      showlegend: false,
    });
  }

  // GPU trace (green, primary y-axis, scaled)
  if (gpu) {
    const scaledValues = gpu.utilization_pct.map((v) => (v * cpu_limit) / 100);
    const customdata = gpu.timestamps.map((_, i) => [
      gpu.memory_used_mb[i],
      gpu.memory_total_mb[i],
      gpu.gpu_count[i],
      gpu.utilization_pct[i],
      gpu.gpu_processes[i],
    ]);
    traces.push({
      x: gpu.timestamps,
      y: scaledValues,
      customdata,
      type: 'scatter',
      mode: 'lines',
      name: 'GPU utilization %',
      yaxis: 'y',
      line: { color: 'green', width: 2 },
      opacity: 0.9,
      hovertemplate:
        '<br><b>Time:</b> %{x}<br>' +
        '<i>GPU utilization</i>: %{customdata[3]:.1f}%' +
        '<br>Memory: %{customdata[0]:.0f} / %{customdata[1]:.0f} MB' +
        '<br>GPUs: %{customdata[2]}' +
        '<br>%{customdata[4]}',
      showlegend: false,
    });
  }

  const layout = {
    title: `CPU and memory usage on ${hostname}`,
    xaxis: { title: 'Time' },
    yaxis: { title: 'CPU usage', range: [0, cpu_limit], side: 'left' },
    yaxis2: { title: 'Memory usage', range: [0, mem_limit], side: 'right', overlaying: 'y' },
    uirevision: 'preserve UI state during updates',
    margin: { t: 40, b: 40, l: 60, r: 60 },
    height: 350,
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
