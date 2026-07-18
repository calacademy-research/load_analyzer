import Plot from '../plot';

export default function ServerChart({ server, proportional = false }) {
  const { hostname, cpu_limit, mem_limit, cpu, mem, gpu, slurm } = server;
  const traces = [];

  // Slurm allocation traces (dashed, colored to match their usage lines:
  // red = memory, blue = CPU; pushed first so usage lines draw on top).
  // Only Slurm nodes have this data; allocation persists on draining nodes.
  if (slurm) {
    // "What's scheduled" hover: the jobs holding each node's reservation,
    // formatted to match the real usage-line hover (a per-entry list under the
    // total). CPU line lists each job's reserved cores; mem line its reserved
    // GB — mirroring how the solid load/mem lines break down by user+cmd. Only
    // populated from when per-node job collection started, so older buckets show
    // just the reserved total.
    const fmtJobs = (jobList, kind) => {
      if (!jobList || jobList.length === 0) return '';
      const lines = jobList.map((j) =>
        kind === 'cpu'
          ? `Host: ${hostname}  user: ${j.user}  cpus: ${j.cpus}  job: ${j.jobid}`
          : `Host: ${hostname}  user: ${j.user}  mem: ${j.mem_gb}G  job: ${j.jobid}`
      );
      return `<br>${lines.join('<br>')}`;
    };
    const cpuJobsHover = (slurm.jobs || []).map((jl) => fmtJobs(jl, 'cpu'));
    const memJobsHover = (slurm.jobs || []).map((jl) => fmtJobs(jl, 'mem'));
    const hasJobs = (slurm.jobs || []).some((jl) => jl && jl.length > 0);
    traces.push({
      x: slurm.timestamps,
      y: slurm.alloc_mem_gb,
      customdata: hasJobs ? memJobsHover : undefined,
      type: 'scatter',
      mode: 'lines',
      name: 'Memory reserved (Slurm)',
      yaxis: 'y2',
      line: { color: 'red', width: 3, dash: 'dash' },
      opacity: 0.55,
      hovertemplate: '<br><b>Time:</b>: %{x}<br><i>Memory reserved</i>: %{y:.1f}G'
        + (hasJobs ? '%{customdata}' : ''),
      showlegend: true,
    });
    traces.push({
      x: slurm.timestamps,
      y: slurm.alloc_cpus,
      customdata: hasJobs ? cpuJobsHover : undefined,
      type: 'scatter',
      mode: 'lines',
      name: 'CPU reserved (Slurm)',
      yaxis: 'y',
      line: { color: 'blue', width: 2, dash: 'dot' },
      opacity: 0.9,
      hovertemplate: '<br><b>Time:</b>: %{x}<br><i>CPU cores reserved</i>: %{y:.1f}'
        + (hasJobs ? '%{customdata}' : ''),
      showlegend: true,
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
      name: 'Memory used',
      yaxis: 'y2',
      line: { color: 'red', width: 3 },
      opacity: 0.7,
      hovertemplate,
      showlegend: true,
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
      name: 'CPU load',
      yaxis: 'y',
      line: { color: 'blue', width: 2 },
      opacity: 1,
      hovertemplate,
      showlegend: true,
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
      showlegend: true,
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
    const prettyT = (s) => `${s.slice(5, 10)} ${s.slice(11, 16)}`;  // "MM-DD HH:MM"
    // Invisible hover targets carrying a plain-language explanation, spread over
    // each drain band so hovering anywhere on the amber region explains it.
    const drainHoverX = [];
    const drainHoverY = [];
    const drainHoverText = [];
    let i = 0;
    while (i < ts.length) {
      if (drain[i]) {
        const startTs = ts[i];
        const bandStart = i;
        while (i < ts.length && drain[i]) i++;
        const ongoing = i >= ts.length;             // drain reaches the latest data
        const lastOn = i - 1;                        // last still-draining sample
        const endTs = ongoing
          ? toNaive(asUtc(ts[lastOn]) + bucketMs)     // extend one bucket
          : ts[i];                                    // first recovered sample
        shapes.push({
          type: 'rect', xref: 'x', yref: 'paper',
          x0: startTs, x1: endTs, y0: 0, y1: 1,
          fillcolor: 'rgba(230,150,50,0.18)', line: { width: 0 }, layer: 'below',
        });
        hasDrain = true;
        const msg = ongoing
          ? `<b>🔧 Automatic patching under way</b><br>`
            + `${hostname} stopped accepting new jobs at ${prettyT(startTs)} so it can install `
            + `system & security updates.<br>`
            + `It's waiting for the jobs still running to finish, then it reboots itself to apply `
            + `them — it comes back on its own. Nothing to do.`
          : `<b>🔧 Automatic patching</b><br>`
            + `${hostname} was paused for system & security updates from ${prettyT(startTs)} to `
            + `${prettyT(endTs)}, then rebooted.<br>Back in service.`;
        // Spread invisible hover targets over the whole band height (several
        // y-levels) so hovering anywhere in the amber region shows the note,
        // not just a thin strip at the top.
        for (let k = bandStart; k <= lastOn; k++) {
          for (const yLevel of [0.12, 0.37, 0.62, 0.87]) {
            drainHoverX.push(ts[k]);
            drainHoverY.push(yLevel);
            drainHoverText.push(msg);
          }
        }
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
    // Legend proxy + invisible top-of-band hover targets for the drain overlay.
    if (hasDrain) {
      traces.push({
        x: [ts[0]], y: [null], type: 'scatter', mode: 'markers',
        marker: { symbol: 'square', size: 12, color: 'rgba(230,150,50,0.55)' },
        name: 'Draining', hoverinfo: 'skip', showlegend: true, legend: 'legend2',
      });
      traces.push({
        x: drainHoverX, y: drainHoverY, customdata: drainHoverText,
        type: 'scatter', mode: 'markers', yaxis: 'y3',
        marker: { size: 18, color: 'rgba(0,0,0,0)' },
        hovertemplate: '%{customdata}<extra></extra>',
        hoverlabel: { bgcolor: 'rgba(120,72,0,0.94)', bordercolor: 'rgba(230,150,50,1)' },
        showlegend: false,
      });
    }
    // Reboot markers double as the legend entry and carry a plain-language note.
    if (hasReboot) {
      traces.push({
        x: slurm.reboots, y: slurm.reboots.map(() => 0),
        type: 'scatter', mode: 'markers', yaxis: 'y',
        marker: { symbol: 'triangle-up', size: 11, color: 'black' },
        name: 'Reboot',
        hovertemplate: '<b>🔄 Automatic patch reboot</b><br>%{x}<br>'
          + 'Rebooted to finish installing system & security updates once its jobs '
          + 'had drained. Back in service.<extra></extra>',
        showlegend: true, legend: 'legend2',
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
    // Hidden [0,1] overlay axis so the drain hover targets sit near the top of
    // the band regardless of whether the data axes are absolute or autoscaled.
    yaxis3: { overlaying: 'y', range: [0, 1], visible: false, fixedrange: true },
    shapes,
    showlegend: true,
    // Left legend: the four data traces (what each line is). Right legend
    // (legend2): the drain/reboot overlays. Both sit inside the plot with a
    // translucent background so they don't hide the series underneath.
    legend: {
      x: 0.01, y: 1, xanchor: 'left', yanchor: 'top',
      bgcolor: 'rgba(255,255,255,0.75)', bordercolor: '#ccc', borderwidth: 1,
      font: { size: 10 },
    },
    legend2: {
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
      config={{ responsive: true, displaylogo: false }}
    />
  );
}
