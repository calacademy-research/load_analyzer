import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Plot from '../plot';

const PROC_COLORS = [
  '#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A',
  '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52',
];

const ALL_HOSTS = [
  'flor', 'rosalindf', 'alice', 'tdobz', 'ibss-spark-1',
  'dirac', 'blackburn', 'rudra', 'kali', 'deepsquid', 'deepsheep',
];

const styles = {
  container: { padding: '16px' },
  controls: {
    display: 'flex', alignItems: 'center', gap: '16px',
    padding: '12px 16px', background: '#f8f9fa', borderRadius: '8px',
    marginBottom: '16px', flexWrap: 'wrap',
  },
  label: { display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px' },
  select: {
    padding: '6px 12px', borderRadius: '4px', border: '1px solid #ccc', fontSize: '14px',
  },
  splitLayout: { display: 'flex', gap: '16px' },
  leftPanel: {
    flex: '0 0 32%', maxHeight: '820px', overflowY: 'auto',
    border: '1px solid #ddd', borderRadius: '8px', background: '#fff',
  },
  rightPanel: { flex: '1 1 68%', maxHeight: '820px', overflowY: 'auto' },
  section: {
    border: '1px solid #ddd', borderRadius: '8px',
    background: '#fff', overflow: 'hidden', marginBottom: '16px',
  },
  sectionHeader: {
    background: '#2c3e50', color: '#fff', padding: '10px 18px',
    fontSize: '18px', fontWeight: 'bold',
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '13px' },
  th: {
    textAlign: 'left', padding: '7px 8px', fontWeight: 'bold',
    backgroundColor: '#f5f5f5', borderBottom: '2px solid #ddd',
    cursor: 'pointer', userSelect: 'none', fontSize: '12px', whiteSpace: 'nowrap',
  },
  td: {
    textAlign: 'left', padding: '5px 8px',
    borderBottom: '1px solid #eee', fontSize: '13px',
  },
  oddRow: { backgroundColor: '#fafafa' },
  detailPanel: {
    padding: '16px', background: '#f8f9fa', borderRadius: '8px',
    border: '1px solid #ddd', marginTop: '16px', fontSize: '14px',
  },
  argText: {
    fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all',
    background: '#fff', padding: '10px', borderRadius: '4px',
    border: '1px solid #eee', overflowY: 'auto',
    whiteSpace: 'pre-wrap', lineHeight: '1.5',
  },
  placeholder: {
    padding: '60px 40px', textAlign: 'center', color: '#888',
    border: '2px dashed #ddd', borderRadius: '8px', fontSize: '15px',
  },
};

function windowButton(active) {
  return {
    padding: '6px 14px', borderRadius: '4px', cursor: 'pointer',
    border: active ? '2px solid #4A90D9' : '1px solid #ccc',
    background: active ? '#e8f0fe' : '#fff',
    fontWeight: active ? 'bold' : 'normal', fontSize: '13px',
  };
}

function formatRuntime(hours) {
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const d = Math.floor(hours / 24);
  const h = Math.round(hours % 24);
  return `${d}d ${h}h`;
}

export default function MyProcessesTab() {
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState('all');
  const [selectedHost, setSelectedHost] = useState('all');
  const [timeWindow, setTimeWindow] = useState('7d');

  const [processes, setProcesses] = useState([]);
  const [processLoading, setProcessLoading] = useState(false);
  const [processError, setProcessError] = useState(null);

  const [checkedKeys, setCheckedKeys] = useState(new Set());
  const [activeProcess, setActiveProcess] = useState(null);

  const [timelines, setTimelines] = useState({});
  const [timelineLoading, setTimelineLoading] = useState(new Set());

  // Draft inputs — the user edits these, but they only hit the server once
  // committed (Search button / Enter) into the applied* values below.
  const [searchTerm, setSearchTerm] = useState('');
  const [startAfter, setStartAfter] = useState('');
  const [startBefore, setStartBefore] = useState('');

  // Applied (committed) query values — these are what the fetch actually sends.
  const [appliedSearch, setAppliedSearch] = useState('');
  const [appliedStart, setAppliedStart] = useState('');
  const [appliedEnd, setAppliedEnd] = useState('');

  const [sortCol, setSortCol] = useState('peak_mem_gb');
  const [sortDir, setSortDir] = useState('desc');

  const processAbort = useRef(null);
  const timelineAborts = useRef({});

  // Fetch user list on mount
  useEffect(() => {
    fetch('/api/users')
      .then((r) => r.json())
      .then((data) => setUsers(data.users || []))
      .catch(() => setUsers([]));
  }, []);

  // Fetch process list when filters change
  useEffect(() => {

    processAbort.current?.abort();
    const controller = new AbortController();
    processAbort.current = controller;

    setProcessLoading(true);
    setProcessError(null);

    const params = new URLSearchParams({
      user: selectedUser,
      host: selectedHost,
      window: timeWindow,
    });
    if (appliedSearch) params.set('search', appliedSearch);
    if (appliedStart) params.set('start', appliedStart);
    if (appliedEnd) params.set('end', appliedEnd);

    fetch(`/api/user-processes?${params}`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        setProcesses(data.processes || []);
        setProcessLoading(false);
        setCheckedKeys(new Set());
        setTimelines({});
        setActiveProcess(null);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setProcessError(err.message);
          setProcessLoading(false);
        }
      });

    return () => controller.abort();
  }, [selectedUser, selectedHost, timeWindow, appliedSearch, appliedStart, appliedEnd]);

  // Commit the draft search box + date range to the server query.
  const applyQuery = useCallback(() => {
    setAppliedSearch(searchTerm.trim());
    setAppliedStart(startAfter);
    setAppliedEnd(startBefore);
  }, [searchTerm, startAfter, startBefore]);

  const clearQuery = useCallback(() => {
    setSearchTerm('');
    setStartAfter('');
    setStartBefore('');
    setAppliedSearch('');
    setAppliedStart('');
    setAppliedEnd('');
  }, []);

  const fetchTimeline = useCallback((host, pid, firstSeen, lastSeen) => {
    const key = `${host}:${pid}`;

    timelineAborts.current[key]?.abort();
    const controller = new AbortController();
    timelineAborts.current[key] = controller;

    setTimelineLoading((prev) => new Set([...prev, key]));

    // Pass the run's own date range so process-history covers it — without
    // this it defaults to the last 7 days and historical runs come back empty
    // (blank chart + Peak Memory shown as 0).
    const params = new URLSearchParams({ host, pid: String(pid) });
    if (firstSeen) params.set('start', firstSeen.slice(0, 10));
    if (lastSeen) params.set('end', lastSeen.slice(0, 10));

    fetch(`/api/process-history?${params}`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        setTimelines((prev) => ({ ...prev, [key]: data }));
        setTimelineLoading((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setTimelineLoading((prev) => {
            const next = new Set(prev);
            next.delete(key);
            return next;
          });
        }
      });
  }, []);

  const selectProcess = useCallback(
    (host, pid, firstSeen, lastSeen) => {
      const key = `${host}:${pid}`;
      setCheckedKeys((prev) => {
        // If already selected, deselect
        if (prev.has(key)) {
          setTimelines((t) => {
            const copy = { ...t };
            delete copy[key];
            return copy;
          });
          return new Set();
        }
        // Replace previous selection with this one
        setTimelines({});
        fetchTimeline(host, pid, firstSeen, lastSeen);
        return new Set([key]);
      });
    },
    [fetchTimeline],
  );

  // Sorting
  const handleSort = (col) => {
    if (col === sortCol) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortCol(col);
      setSortDir('desc');
    }
  };
  const arrow = (col) => (col === sortCol ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : '');

  // Search and date filtering now happen server-side (see applyQuery), so the
  // client just sorts whatever the server returned.
  const sortedProcesses = useMemo(() => {
    return [...processes].sort((a, b) => {
      const av = a[sortCol];
      const bv = b[sortCol];
      if (typeof av === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortDir === 'asc' ? av - bv : bv - av;
    });
  }, [processes, sortCol, sortDir]);

  // Build chart traces
  const { cpuTraces, memTraces } = useMemo(() => {
    const cpu = [];
    const mem = [];
    let colorIdx = 0;

    for (const key of checkedKeys) {
      const tl = timelines[key];
      if (!tl || !tl.timestamps || tl.timestamps.length === 0) continue;

      const [host, pidStr] = key.split(':');
      const color = PROC_COLORS[colorIdx % PROC_COLORS.length];
      const label = `${tl.comm}:${pidStr} (${host})`;

      cpu.push({
        x: tl.timestamps,
        y: tl.cpu_cores,
        type: 'scatter',
        mode: 'lines',
        name: label,
        line: { color, width: 2 },
        hovertemplate: `<b>${label}</b><br>%{x}<br>CPU: %{y:.2f} cores<extra></extra>`,
      });

      mem.push({
        x: tl.timestamps,
        y: tl.mem_gb,
        type: 'scatter',
        mode: 'lines',
        name: label,
        line: { color, width: 2 },
        hovertemplate: `<b>${label}</b><br>%{x}<br>Memory: %{y:.2f} GB<extra></extra>`,
      });

      colorIdx++;
    }
    return { cpuTraces: cpu, memTraces: mem };
  }, [checkedKeys, timelines]);

  const cpuLayout = {
    title: { text: 'CPU Usage Over Time', font: { size: 16 } },
    xaxis: { title: 'Time' },
    yaxis: { title: 'CPU Cores', rangemode: 'tozero' },
    height: 220,
    margin: { t: 40, b: 50, l: 60, r: 30 },
    showlegend: true,
    legend: { orientation: 'h', y: -0.25, font: { size: 12 } },
    hovermode: 'x unified',
    uirevision: 'cpu',
  };

  const memLayout = {
    title: { text: 'Memory Usage Over Time', font: { size: 16 } },
    xaxis: { title: 'Time' },
    yaxis: { title: 'Memory (GB)', rangemode: 'tozero' },
    height: 220,
    margin: { t: 40, b: 50, l: 60, r: 30 },
    showlegend: true,
    legend: { orientation: 'h', y: -0.25, font: { size: 12 } },
    hovermode: 'x unified',
    uirevision: 'mem',
  };

  const detailTl =
    activeProcess && timelines[`${activeProcess.host}:${activeProcess.pid}`];

  return (
    <div style={styles.container}>
      {/* Controls */}
      <div style={styles.controls}>
        <label style={styles.label}>
          User:
          <select
            value={selectedUser}
            onChange={(e) => setSelectedUser(e.target.value)}
            style={styles.select}
          >
            <option value="all">All Users</option>
            {users.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </label>

        <label style={styles.label}>
          Host:
          <select
            value={selectedHost}
            onChange={(e) => setSelectedHost(e.target.value)}
            style={styles.select}
          >
            <option value="all">All Hosts</option>
            {ALL_HOSTS.map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </select>
        </label>

        <div style={{ display: 'flex', gap: '4px' }}>
          {[
            ['active', 'Active Now'],
            ['24h', 'Last 24h'],
            ['7d', 'Last 7d'],
            ['30d', 'Last 30d'],
            ['90d', 'Last 90d'],
            ['all', 'All Time'],
          ].map(([val, label]) => (
            <button
              key={val}
              style={windowButton(timeWindow === val)}
              onClick={() => {
                // A preset window and an explicit date range are mutually
                // exclusive — picking a preset drops the date range.
                setTimeWindow(val);
                setStartAfter('');
                setStartBefore('');
                setAppliedStart('');
                setAppliedEnd('');
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {processLoading && (
          <span style={{ fontSize: '13px', color: '#4A90D9' }}>Loading...</span>
        )}
        {!processLoading && (
          <span style={{ fontSize: '13px', color: '#666' }}>
            {processes.length} process{processes.length !== 1 ? 'es' : ''}
            {(appliedSearch || appliedStart || appliedEnd) && ' matching'}
            {processes.length >= 500 && (
              <span style={{ color: '#c0392b' }}> (capped at 500 — narrow your search)</span>
            )}
          </span>
        )}
      </div>

      {/* Main content */}
      {processLoading && processes.length === 0 ? (
        <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
          Loading processes...
        </div>
      ) : processError ? (
        <div style={{ padding: '20px', color: 'red' }}>Error: {processError}</div>
      ) : (
        <div style={styles.splitLayout}>
          {/* Left: process table */}
          <div style={styles.leftPanel}>
            <div style={{ padding: '8px', borderBottom: '1px solid #eee', position: 'sticky', top: 0, background: '#fff', zIndex: 1 }}>
              <input
                type="text"
                placeholder="Search all runs by command, args, host, user... then click Search"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') applyQuery(); }}
                style={{
                  width: '100%', padding: '6px 10px', fontSize: '13px',
                  border: '1px solid #ccc', borderRadius: '4px',
                  boxSizing: 'border-box',
                }}
              />
              <div style={{ display: 'flex', gap: '6px', marginTop: '6px', alignItems: 'center', fontSize: '12px', color: '#555', flexWrap: 'wrap' }}>
                <span>Started:</span>
                <input type="date" value={startAfter} onChange={(e) => setStartAfter(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') applyQuery(); }}
                  style={{ fontSize: '12px', padding: '3px 4px', border: '1px solid #ccc', borderRadius: '3px' }} />
                <span>to</span>
                <input type="date" value={startBefore} onChange={(e) => setStartBefore(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') applyQuery(); }}
                  style={{ fontSize: '12px', padding: '3px 4px', border: '1px solid #ccc', borderRadius: '3px' }} />
                <button onClick={applyQuery}
                  style={{ fontSize: '12px', fontWeight: 'bold', padding: '3px 12px', cursor: 'pointer', border: '1px solid #4A90D9', borderRadius: '3px', background: '#e8f0fe', color: '#1a5fb4' }}>
                  Search
                </button>
                {(searchTerm || startAfter || startBefore || appliedSearch || appliedStart || appliedEnd) && (
                  <button onClick={clearQuery}
                    style={{ fontSize: '11px', padding: '2px 6px', cursor: 'pointer', border: '1px solid #ccc', borderRadius: '3px', background: '#fff' }}>
                    Clear
                  </button>
                )}
              </div>
              {(appliedSearch || appliedStart || appliedEnd) && (
                <div style={{ fontSize: '11px', color: '#888', marginTop: '3px' }}>
                  Showing {sortedProcesses.length} result{sortedProcesses.length !== 1 ? 's' : ''}
                  {appliedSearch && ` for "${appliedSearch}"`}
                  {(appliedStart || appliedEnd) && ` (started ${appliedStart || '…'} to ${appliedEnd || '…'})`}
                </div>
              )}
            </div>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={{ ...styles.th, width: '28px' }}></th>
                  <th style={styles.th} onClick={() => handleSort('username')}>
                    User{arrow('username')}
                  </th>
                  <th style={styles.th} onClick={() => handleSort('comm')}>
                    Command{arrow('comm')}
                  </th>
                  <th style={styles.th} onClick={() => handleSort('pid')}>
                    PID{arrow('pid')}
                  </th>
                  <th style={styles.th} onClick={() => handleSort('host')}>
                    Host{arrow('host')}
                  </th>
                  <th style={styles.th} onClick={() => handleSort('first_seen')}>
                    Started{arrow('first_seen')}
                  </th>
                  <th style={styles.th} onClick={() => handleSort('peak_mem_gb')}>
                    Mem GB{arrow('peak_mem_gb')}
                  </th>
                  <th style={styles.th} onClick={() => handleSort('threads')}>
                    Thr{arrow('threads')}
                  </th>
                  <th style={styles.th} onClick={() => handleSort('runtime_hours')}>
                    Runtime{arrow('runtime_hours')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedProcesses.map((proc, i) => {
                  const key = `${proc.host}:${proc.pid}`;
                  const isChecked = checkedKeys.has(key);
                  const isActive =
                    activeProcess &&
                    activeProcess.host === proc.host &&
                    activeProcess.pid === proc.pid;
                  return (
                    <tr
                      key={key}
                      style={{
                        ...(i % 2 ? styles.oddRow : {}),
                        ...(isActive ? { background: '#e8f0fe' } : {}),
                        cursor: 'pointer',
                      }}
                      onClick={() => {
                        setActiveProcess(proc);
                        selectProcess(proc.host, proc.pid, proc.first_seen, proc.last_seen);
                      }}
                    >
                      <td style={styles.td}>
                        <input
                          type="radio"
                          name="process-select"
                          checked={isChecked}
                          onChange={() => selectProcess(proc.host, proc.pid, proc.first_seen, proc.last_seen)}
                          onClick={(e) => e.stopPropagation()}
                          style={{ cursor: 'pointer' }}
                        />
                      </td>
                      <td style={{ ...styles.td, fontSize: '12px' }}>{proc.username}</td>
                      <td
                        style={{
                          ...styles.td,
                          maxWidth: '140px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontWeight: '500',
                        }}
                        title={`PID ${proc.pid}: ${proc.args}`}
                      >
                        {proc.comm}
                      </td>
                      <td style={{ ...styles.td, fontSize: '12px', color: '#666' }}>{proc.pid}</td>
                      <td style={styles.td}>{proc.host}</td>
                      <td style={{ ...styles.td, fontSize: '12px', whiteSpace: 'nowrap' }}>{proc.first_seen.replace(/:\d\d$/, '')}</td>
                      <td style={styles.td}>{proc.peak_mem_gb.toFixed(1)}</td>
                      <td style={styles.td}>{proc.threads}</td>
                      <td style={styles.td}>{formatRuntime(proc.runtime_hours)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {processes.length === 0 && (
              <div style={{ padding: '24px', textAlign: 'center', color: '#888' }}>
                No processes found.
              </div>
            )}
          </div>

          {/* Right: charts + detail */}
          <div style={styles.rightPanel}>
            {checkedKeys.size === 0 && timelineLoading.size === 0 ? (
              <div style={styles.placeholder}>
                Select a process to view resource usage over time.
              </div>
            ) : (
              <>
                {timelineLoading.size > 0 && (
                  <div
                    style={{
                      padding: '8px 16px',
                      fontSize: '13px',
                      color: '#4A90D9',
                      marginBottom: '8px',
                    }}
                  >
                    Loading timeline data...
                  </div>
                )}
                {cpuTraces.length > 0 && (
                  <>
                    <div style={styles.section}>
                      <div style={styles.sectionHeader}>CPU Usage</div>
                      <div style={{ padding: '4px 8px' }}>
                        <Plot
                          data={cpuTraces}
                          layout={cpuLayout}
                          useResizeHandler
                          style={{ width: '100%' }}
                          config={{ responsive: true }}
                        />
                      </div>
                    </div>
                    <div style={styles.section}>
                      <div style={styles.sectionHeader}>Memory Usage</div>
                      <div style={{ padding: '4px 8px' }}>
                        <Plot
                          data={memTraces}
                          layout={memLayout}
                          useResizeHandler
                          style={{ width: '100%' }}
                          config={{ responsive: true }}
                        />
                      </div>
                    </div>
                  </>
                )}
              </>
            )}

            {/* Detail panel */}
            {activeProcess && (
              <div style={styles.detailPanel}>
                <h3 style={{ margin: '0 0 12px', fontSize: '16px' }}>
                  {activeProcess.comm}{' '}
                  <span style={{ fontWeight: 'normal', color: '#666' }}>
                    PID {activeProcess.pid} on {activeProcess.host}
                  </span>
                </h3>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr 1fr',
                    gap: '8px 16px',
                    marginBottom: '12px',
                    fontSize: '13px',
                  }}
                >
                  <div>
                    <strong>Runtime:</strong> {formatRuntime(activeProcess.runtime_hours)}
                  </div>
                  <div>
                    <strong>Peak Memory:</strong>{' '}
                    {(detailTl?.peak_mem_gb ?? activeProcess.peak_mem_gb).toFixed(2)} GB
                  </div>
                  <div>
                    <strong>CPU Time:</strong>{' '}
                    {(
                      detailTl?.total_cpu_seconds ?? activeProcess.cpu_seconds
                    ).toLocaleString()}
                    s
                  </div>
                  <div>
                    <strong>Threads:</strong> {activeProcess.threads}
                  </div>
                  <div>
                    <strong>Parent PID:</strong> {detailTl?.ppid ?? 'N/A'}
                  </div>
                  <div>
                    <strong>Snapshots:</strong> {activeProcess.snapshot_count}
                  </div>
                  <div>
                    <strong>First Seen:</strong>{' '}
                    {detailTl?.first_seen || activeProcess.first_seen}
                  </div>
                  <div>
                    <strong>Last Seen:</strong>{' '}
                    {detailTl?.last_seen || activeProcess.last_seen}
                  </div>
                  {detailTl?.segments > 1 && (
                    <div style={{ color: '#D94A7A' }}>
                      <strong>PID Reused:</strong> {detailTl.segments} times (showing latest)
                    </div>
                  )}
                </div>

                <div>
                  <strong>Full Command:</strong>
                  <div style={styles.argText}>
                    {detailTl?.args || activeProcess.args}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
