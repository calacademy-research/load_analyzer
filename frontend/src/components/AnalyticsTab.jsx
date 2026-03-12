import { useState, useEffect, useMemo } from 'react';
import { useServerData } from '../hooks/useServerData';
import Plot from 'react-plotly.js';
import DateRangeSlider from './DateRangeSlider';

const SERVER_COLORS = {
  flor: '#4A90D9',
  rosalindf: '#D94A7A',
  alice: '#50B88C',
  tdobz: '#D9944A',
  'ibss-spark-1': '#7B5CB0',
};

const sectionStyle = {
  marginBottom: '32px',
  border: '1px solid #ddd',
  borderRadius: '8px',
  background: '#fff',
  overflow: 'hidden',
};

const sectionHeader = {
  background: '#2c3e50',
  color: '#fff',
  padding: '12px 18px',
  fontSize: '20px',
  fontWeight: 'bold',
};

const tableStyles = {
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '18px' },
  th: {
    textAlign: 'left', padding: '10px 14px', fontWeight: 'bold',
    backgroundColor: '#f5f5f5', borderBottom: '2px solid #ddd',
    cursor: 'pointer', userSelect: 'none', fontSize: '18px',
  },
  td: { textAlign: 'left', padding: '10px 14px', borderBottom: '1px solid #eee', fontSize: '18px' },
  oddRow: { backgroundColor: '#fafafa' },
};

function SortableTable({ columns, rows, defaultSort, defaultAsc = false }) {
  const [sortCol, setSortCol] = useState(defaultSort);
  const [sortAsc, setSortAsc] = useState(defaultAsc);
  const [filter, setFilter] = useState('');

  const sorted = useMemo(() => {
    let filtered = [...rows];
    if (filter) {
      const f = filter.toLowerCase();
      filtered = filtered.filter((r) =>
        columns.some((c) => String(r[c.key] ?? '').toLowerCase().includes(f)),
      );
    }
    filtered.sort((a, b) => {
      const av = a[sortCol] ?? -Infinity;
      const bv = b[sortCol] ?? -Infinity;
      if (av < bv) return sortAsc ? -1 : 1;
      if (av > bv) return sortAsc ? 1 : -1;
      return 0;
    });
    return filtered;
  }, [rows, columns, sortCol, sortAsc, filter]);

  const handleSort = (col) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(false); }
  };
  const arrow = (col) => (sortCol === col ? (sortAsc ? ' ▲' : ' ▼') : '');

  return (
    <div style={{ padding: '12px' }}>
      <input
        type="text"
        placeholder="Filter..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{
          padding: '8px 12px', fontSize: '18px', border: '1px solid #ccc',
          borderRadius: '4px', marginBottom: '10px', width: '300px',
        }}
      />
      <table style={tableStyles.table}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} style={tableStyles.th} onClick={() => handleSort(col.key)}>
                {col.label}{arrow(col.key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={row._key || i} style={i % 2 === 1 ? tableStyles.oddRow : undefined}>
              {columns.map((col) => (
                <td key={col.key} style={tableStyles.td}>
                  {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ServerBreakdown({ servers }) {
  if (!servers || Object.keys(servers).length === 0) return null;
  return (
    <span style={{ fontSize: '16px', color: '#666', marginLeft: '8px' }}>
      ({Object.entries(servers).map(([h, v]) => `${h}: ${v}`).join(', ')})
    </span>
  );
}

export default function AnalyticsTab() {
  const fmt = (d) => d.toISOString().split('T')[0];
  const today = new Date();
  const oneMonthAgo = new Date(today);
  oneMonthAgo.setMonth(oneMonthAgo.getMonth() - 1);

  const [startDate, setStartDate] = useState(fmt(oneMonthAgo));
  const [endDate, setEndDate] = useState(fmt(today));
  const [dataStart, setDataStart] = useState(null);
  const { data, loading, error } = useServerData('analytics', startDate, endDate);
  const { data: slurmData } = useServerData('slurm-efficiency', startDate, endDate);

  useEffect(() => {
    fetch('/api/config').then(r => r.json()).then(cfg => {
      if (cfg.data_start) setDataStart(cfg.data_start);
    }).catch(() => {});
  }, []);

  const dateControls = (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '16px',
      padding: '12px 16px', background: '#f8f9fa', borderBottom: '1px solid #e0e0e0',
      flexWrap: 'wrap',
    }}>
      <div style={{ flex: '1 1 600px', minWidth: '300px' }}>
        <DateRangeSlider
          startDate={startDate} endDate={endDate}
          onStartChange={setStartDate} onEndChange={setEndDate}
          minDate={dataStart}
        />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
          style={{ padding: '6px 10px', fontSize: '14px', border: '1px solid #ccc', borderRadius: '4px' }} />
        <span>to</span>
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
          style={{ padding: '6px 10px', fontSize: '14px', border: '1px solid #ccc', borderRadius: '4px' }} />
      </div>
    </div>
  );

  if (error && !data) return <>{dateControls}<div style={{ padding: '20px', color: 'red' }}>Error: {error}</div></>;
  if (!data) return <>{dateControls}<div style={{ padding: '40px', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}><div style={{ width: '24px', height: '24px', border: '3px solid #ddd', borderTopColor: '#4A90D9', borderRadius: '50%', animation: 'analytics-spin 0.8s linear infinite' }} /> Loading...</div></>;

  const { users_by_cpu, users_by_mem, server_utilization, top_programs } = data;

  // Server utilization bar chart
  const serverNames = server_utilization.map((s) => s.hostname);
  const serverCpuAvg = server_utilization.map((s) => s.avg_cpu_pct);
  const serverCpuPeak = server_utilization.map((s) => s.peak_cpu_pct);
  const serverMemAvg = server_utilization.map((s) => s.avg_mem_pct);
  const serverColors = serverNames.map((h) => SERVER_COLORS[h] || '#888');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', padding: '0', position: 'relative' }}>
      {dateControls}

      {/* Loading overlay */}
      {loading && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(255,255,255,0.5)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          pointerEvents: 'none',
        }}>
          <div style={{
            fontSize: '20px', color: '#333', display: 'flex', alignItems: 'center', gap: '12px',
            background: 'white', padding: '20px 32px', borderRadius: '12px',
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
          }}>
            <div style={{
              width: '36px', height: '36px',
              border: '4px solid #e0e0e0', borderTopColor: '#4A90D9',
              borderRadius: '50%',
              animation: 'analytics-spin 0.8s linear infinite',
            }} />
            Updating...
          </div>
        </div>
      )}

      {/* Server Utilization */}
      <div style={sectionStyle}>
        <div style={sectionHeader}>Server Utilization</div>
        <div style={{ padding: '8px' }}>
          <Plot
            data={[
              {
                y: serverNames, x: serverCpuAvg, type: 'bar', orientation: 'h',
                name: 'Avg CPU %', marker: { color: serverColors, opacity: 0.7 },
                text: serverCpuAvg.map((v) => `${v}%`), textposition: 'auto', textfont: { size: 15 },
                hovertemplate: '<b>%{y}</b><br>Avg CPU: %{x:.1f}%<extra></extra>',
              },
              {
                y: serverNames, x: serverCpuPeak, type: 'bar', orientation: 'h',
                name: 'Peak CPU %', marker: { color: serverColors, opacity: 0.3 },
                hovertemplate: '<b>%{y}</b><br>Peak CPU: %{x:.1f}%<extra></extra>',
              },
            ]}
            layout={{
              title: { text: 'CPU Utilization (% of capacity)', font: { size: 20 } },
              xaxis: { title: { text: '% of total cores', font: { size: 16 } }, range: [0, 100], tickfont: { size: 15 } },
              yaxis: { automargin: true, tickfont: { size: 16 } },
              barmode: 'overlay',
              margin: { l: 140, r: 30, t: 50, b: 50 },
              height: 260,
              showlegend: true,
              legend: { orientation: 'h', y: -0.3, font: { size: 15 } },
              font: { size: 15 },
            }}
            useResizeHandler
            style={{ width: '100%' }}
            config={{ responsive: true }}
          />
        </div>
        <SortableTable
          columns={[
            { key: 'hostname', label: 'Server' },
            { key: 'cpu_limit', label: 'Cores' },
            { key: 'mem_limit', label: 'RAM (GB)' },
            { key: 'avg_cpu_pct', label: 'Avg CPU %' },
            { key: 'peak_cpu_pct', label: 'Peak CPU %' },
            { key: 'avg_mem_pct', label: 'Avg Mem %' },
            { key: 'peak_mem_pct', label: 'Peak Mem %' },
            { key: 'total_core_hours', label: 'Core-Hours' },
          ]}
          rows={server_utilization.map((s) => ({ ...s, _key: s.hostname }))}
          defaultSort="total_core_hours"
        />
      </div>

      {/* Top Users by Core-Hours */}
      <div style={sectionStyle}>
        <div style={sectionHeader}>Top Users by Core-Hours</div>
        <div style={{ padding: '8px' }}>
          <Plot
            data={[
              {
                y: users_by_cpu.slice(0, 15).map((u) => u.user).reverse(),
                x: users_by_cpu.slice(0, 15).map((u) => u.core_hours).reverse(),
                type: 'bar', orientation: 'h',
                marker: { color: '#4A90D9' },
                text: users_by_cpu.slice(0, 15).map((u) => `${u.core_hours}`).reverse(),
                textposition: 'auto', textfont: { size: 15 },
                hovertemplate: '<b>%{y}</b>: %{x:.1f} core-hours<extra></extra>',
              },
            ]}
            layout={{
              title: { text: 'Core-Hours by User', font: { size: 20 } },
              xaxis: { title: { text: 'Core-Hours', font: { size: 16 } }, tickfont: { size: 15 } },
              yaxis: { automargin: true, tickfont: { size: 16 } },
              margin: { l: 140, r: 30, t: 50, b: 50 },
              height: Math.max(300, users_by_cpu.slice(0, 15).length * 36),
              font: { size: 15 },
            }}
            useResizeHandler
            style={{ width: '100%' }}
            config={{ responsive: true }}
          />
        </div>
        <SortableTable
          columns={[
            { key: 'user', label: 'User' },
            { key: 'core_hours', label: 'Core-Hours' },
            {
              key: 'servers', label: 'Breakdown',
              render: (v) => v ? Object.entries(v).map(([h, val]) => `${h}: ${val}`).join(', ') : '—',
            },
          ]}
          rows={users_by_cpu.map((u) => ({ ...u, _key: u.user }))}
          defaultSort="core_hours"
        />
      </div>

      {/* Top Users by GB-Hours */}
      <div style={sectionStyle}>
        <div style={sectionHeader}>Top Users by Memory (GB-Hours)</div>
        <div style={{ padding: '8px' }}>
          <Plot
            data={[
              {
                y: users_by_mem.slice(0, 15).map((u) => u.user).reverse(),
                x: users_by_mem.slice(0, 15).map((u) => u.gb_hours).reverse(),
                type: 'bar', orientation: 'h',
                marker: { color: '#D94A7A' },
                text: users_by_mem.slice(0, 15).map((u) => `${u.gb_hours}`).reverse(),
                textposition: 'auto', textfont: { size: 15 },
                hovertemplate: '<b>%{y}</b>: %{x:.1f} GB-hours<extra></extra>',
              },
            ]}
            layout={{
              title: { text: 'GB-Hours by User', font: { size: 20 } },
              xaxis: { title: { text: 'GB-Hours', font: { size: 16 } }, tickfont: { size: 15 } },
              yaxis: { automargin: true, tickfont: { size: 16 } },
              margin: { l: 140, r: 30, t: 50, b: 50 },
              height: Math.max(300, users_by_mem.slice(0, 15).length * 36),
              font: { size: 15 },
            }}
            useResizeHandler
            style={{ width: '100%' }}
            config={{ responsive: true }}
          />
        </div>
        <SortableTable
          columns={[
            { key: 'user', label: 'User' },
            { key: 'gb_hours', label: 'GB-Hours' },
            {
              key: 'servers', label: 'Breakdown',
              render: (v) => v ? Object.entries(v).map(([h, val]) => `${h}: ${val}`).join(', ') : '—',
            },
          ]}
          rows={users_by_mem.map((u) => ({ ...u, _key: u.user }))}
          defaultSort="gb_hours"
        />
      </div>

      {/* Top Programs */}
      <div style={sectionStyle}>
        <div style={sectionHeader}>Top Programs</div>
        <SortableTable
          columns={[
            { key: 'rank', label: '#' },
            { key: 'program', label: 'Program' },
            { key: 'core_hours', label: 'Core-Hours' },
            { key: 'gb_hours', label: 'GB-Hours' },
            {
              key: 'users', label: 'Users',
              render: (v) => v ? v.join(', ') : '—',
            },
          ]}
          rows={top_programs.map((p, i) => ({ ...p, rank: i + 1, _key: p.program }))}
          defaultSort="core_hours"
        />
      </div>

      {/* Slurm Allocation Efficiency */}
      {slurmData && slurmData.user_summary && slurmData.user_summary.length > 0 && (
        <div style={sectionStyle}>
          <div style={sectionHeader}>Slurm Allocation Efficiency</div>
          <div style={{ padding: '8px' }}>
            <Plot
              data={[
                {
                  y: slurmData.user_summary.slice(0, 15).map((u) => u.username).reverse(),
                  x: slurmData.user_summary.slice(0, 15).map((u) => u.total_wasted_gb_hours).reverse(),
                  type: 'bar', orientation: 'h',
                  marker: { color: '#D94A7A' },
                  text: slurmData.user_summary.slice(0, 15).map((u) => `${u.total_wasted_gb_hours}`).reverse(),
                  textposition: 'auto', textfont: { size: 15 },
                  hovertemplate: '<b>%{y}</b>: %{x:.1f} wasted GB-hours<extra></extra>',
                },
              ]}
              layout={{
                title: { text: 'Wasted GB-Hours by User (Requested − Used)', font: { size: 20 } },
                xaxis: { title: { text: 'Wasted GB-Hours', font: { size: 16 } }, tickfont: { size: 15 } },
                yaxis: { automargin: true, tickfont: { size: 16 } },
                margin: { l: 140, r: 30, t: 50, b: 50 },
                height: Math.max(300, slurmData.user_summary.slice(0, 15).length * 36),
                font: { size: 15 },
              }}
              useResizeHandler
              style={{ width: '100%' }}
              config={{ responsive: true }}
            />
          </div>
          <SortableTable
            columns={[
              { key: 'username', label: 'User' },
              { key: 'job_count', label: 'Jobs' },
              { key: 'avg_req_mem_gb', label: 'Avg Requested (GB)' },
              { key: 'avg_max_rss_gb', label: 'Avg Used (GB)' },
              {
                key: 'avg_mem_efficiency', label: 'Efficiency',
                render: (v) => v != null ? `${v}%` : '—',
              },
              { key: 'total_wasted_gb_hours', label: 'Wasted GB-Hours' },
            ]}
            rows={slurmData.user_summary.map((u) => ({ ...u, _key: u.username }))}
            defaultSort="total_wasted_gb_hours"
          />
        </div>
      )}

      {/* Slurm Jobs Detail */}
      {slurmData && slurmData.jobs && slurmData.jobs.length > 0 && (
        <div style={sectionStyle}>
          <div style={sectionHeader}>Recent Slurm Jobs</div>
          <SortableTable
            columns={[
              { key: 'job_id', label: 'Job ID' },
              { key: 'username', label: 'User' },
              { key: 'alloc_cpus', label: 'CPUs' },
              { key: 'req_mem_gb', label: 'Req Mem (GB)' },
              { key: 'max_rss_gb', label: 'Used Mem (GB)' },
              {
                key: 'mem_efficiency', label: 'Efficiency',
                render: (v) => v != null ? `${v}%` : '—',
              },
              { key: 'elapsed_hours', label: 'Hours' },
              { key: 'state', label: 'State' },
              { key: 'start_time', label: 'Started' },
            ]}
            rows={slurmData.jobs.map((j) => ({ ...j, _key: j.job_id }))}
            defaultSort="start_time"
          />
        </div>
      )}
    </div>
  );
}
