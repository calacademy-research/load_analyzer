import Plot from '../plot';

export default function ServerChart({ server, proportional = false }) {
  const { hostname, cpu_limit, mem_limit, cpu, mem, gpu, slurm } = server;
  const traces = [];

  // Slurm allocation traces (dashed, colored to match their usage lines:
  // red = memory, blue = CPU; pushed first so usage lines draw on top).
  // Only Slurm nodes have this data; allocation persists on draining nodes.
  if (slurm) {
    traces.push({
      x: slurm.timestamps,
      y: slurm.alloc_mem_gb,
      type: 'scatter',
      mode: 'lines',
      name: 'Slurm mem alloc',
      yaxis: 'y2',
      line: { color: 'red', width: 3, dash: 'dash' },
      opacity: 0.55,
      hovertemplate: '<br><b>Time:</b>: %{x}<br><i>Slurm mem allocated</i>: %{y:.1f}G',
      showlegend: false,
    });
    traces.push({
      x: slurm.timestamps,
      y: slurm.alloc_cpus,
      type: 'scatter',
      mode: 'lines',
      name: 'Slurm CPU alloc',
      yaxis: 'y',
      line: { color: 'blue', width: 2, dash: 'dot' },
      opacity: 0.9,
      hovertemplate: '<br><b>Time:</b>: %{x}<br><i>Slurm CPUs allocated</i>: %{y:.1f}',
      showlegend: false,
    });
  }

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

  // Node-state overlays (Slurm nodes only): amber bands mark stretches where
  // the node was draining (state carried the DRAIN flag), and vertical black
  // bars mark reboot events (BootTime jumped forward). Both are drawn as
  // layout shapes so they span the full chart height regardless of y-scale.
  const shapes = [];
  let hasDrain = false;
  let hasReboot = false;
  if (slurm) {
    const ts = slurm.timestamps || [];
    const drain = slurm.drain || [];
    // Timestamps are naive ISO strings that Plotly plots in UTC; parse them the
    // same way (append 'Z') so any computed edge stays on the same axis. A naive
    // `new Date(str)` would be read as local time and land hours off.
    const asUtc = (s) => Date.parse(s + 'Z');
    const toNaive = (ms) => new Date(ms).toISOString().slice(0, 19);
    // One bucket's worth of time, so a band (or a just-started drain that only
    // touches the last sample) has visible width rather than collapsing to a line.
    const bucketMs = ts.length > 1 ? (asUtc(ts[1]) - asUtc(ts[0])) : 5 * 60 * 1000;
    let i = 0;
    while (i < ts.length) {
      if (drain[i]) {
        const startTs = ts[i];
        while (i < ts.length && drain[i]) i++;
        const lastOn = i - 1;                       // last still-draining sample
        const endTs = i < ts.length
          ? ts[i]                                    // first recovered sample
          : toNaive(asUtc(ts[lastOn]) + bucketMs);   // ongoing: extend one bucket
        shapes.push({
          type: 'rect', xref: 'x', yref: 'paper',
          x0: startTs, x1: endTs, y0: 0, y1: 1,
          fillcolor: 'rgba(230,150,50,0.18)', line: { width: 0 }, layer: 'below',
        });
        hasDrain = true;
      } else {
        i++;
      }
    }
    (slurm.reboots || []).forEach((t) => {
      shapes.push({
        type: 'line', xref: 'x', yref: 'paper',
        x0: t, x1: t, y0: 0, y1: 1,
        line: { color: 'black', width: 1.5 }, layer: 'above',
      });
      hasReboot = true;
    });
    // Legend proxies + hoverable reboot markers so the overlays are labeled.
    if (hasDrain) {
      traces.push({
        x: [ts[0]], y: [null], type: 'scatter', mode: 'markers',
        marker: { symbol: 'square', size: 12, color: 'rgba(230,150,50,0.55)' },
        name: 'Draining', hoverinfo: 'skip', showlegend: true,
      });
    }
    if (hasReboot) {
      traces.push({
        x: slurm.reboots, y: slurm.reboots.map(() => 0),
        type: 'scatter', mode: 'markers', yaxis: 'y',
        marker: { symbol: 'triangle-up', size: 10, color: 'black' },
        name: 'Reboot', hovertemplate: '<b>Reboot</b><br>%{x}<extra></extra>',
        showlegend: true,
      });
    }
  }

  // Absolute scaling (default): axes fixed to the machine's full spec so
  // charts are comparable and headroom is visible. Proportional (header
  // button): autoscale, so brief spikes above capacity stay visible.
  const layout = {
    title: `CPU and memory usage on ${hostname}`,
    xaxis: { title: 'Time' },
    yaxis: {
      title: 'CPU usage', rangemode: 'tozero', side: 'left',
      ...(proportional ? {} : { range: [0, cpu_limit] }),
    },
    yaxis2: {
      title: 'Memory usage', rangemode: 'tozero', side: 'right', overlaying: 'y',
      ...(proportional ? {} : { range: [0, mem_limit] }),
    },
    shapes,
    showlegend: hasDrain || hasReboot,
    legend: {
      x: 1, y: 1, xanchor: 'right', yanchor: 'top',
      bgcolor: 'rgba(255,255,255,0.6)', font: { size: 10 },
    },
    // Keyed to the axis mode: same value preserves zoom/pan across data
    // refreshes; a mode toggle changes it so the new ranges actually apply.
    uirevision: proportional ? 'proportional' : 'absolute',
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
