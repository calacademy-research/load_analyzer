import { useServerData } from '../hooks/useServerData';
import Plot from '../plot';

const styles = {
  container: { padding: '16px' },
  updated: { fontSize: '12px', color: '#888', marginBottom: '14px' },
  cards: { display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' },
  card: {
    flex: '1 1 340px', border: '1px solid #ddd', borderRadius: '8px',
    background: '#fff', padding: '18px 22px',
  },
  cardTitle: { fontSize: '16px', fontWeight: 'bold', color: '#2c3e50' },
  cardSub: { fontSize: '12px', color: '#888', marginBottom: '12px' },
  bigNum: { fontSize: '30px', fontWeight: 'bold', color: '#2c3e50' },
  bigNumUnit: { fontSize: '15px', fontWeight: 'normal', color: '#666' },
  track: {
    position: 'relative', height: '28px', background: '#e9ecef',
    borderRadius: '14px', overflow: 'hidden', marginTop: '12px',
  },
  section: {
    border: '1px solid #ddd', borderRadius: '8px',
    background: '#fff', overflow: 'hidden', marginBottom: '16px',
  },
  sectionHeader: {
    background: '#2c3e50', color: '#fff', padding: '10px 18px',
    fontSize: '17px', fontWeight: 'bold',
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '13px' },
  th: {
    textAlign: 'left', padding: '8px 10px', backgroundColor: '#f5f5f5',
    borderBottom: '2px solid #ddd', fontSize: '12px',
  },
  td: { padding: '6px 10px', borderBottom: '1px solid #eee' },
  loading: { padding: '40px', textAlign: 'center', color: '#888' },
};

function utilColor(pct) {
  if (pct == null) return '#adb5bd';
  if (pct >= 90) return '#EF553B';
  if (pct >= 70) return '#FFA15A';
  return '#00A86B';
}

function CapacityCard({ title, used, total, unit, nodes }) {
  const pct = total > 0 ? (100 * used) / total : 0;
  const free = Math.max(0, total - used);
  return (
    <div style={styles.card}>
      <div style={styles.cardTitle}>{title}</div>
      <div style={styles.cardSub}>
        {nodes} node{nodes !== 1 ? 's' : ''} currently accepting Slurm jobs
      </div>
      <div style={styles.bigNum}>
        {used.toLocaleString()}{' '}
        <span style={styles.bigNumUnit}>/ {total.toLocaleString()} {unit} used</span>
      </div>
      <div style={styles.track}>
        <div
          style={{
            position: 'absolute', top: 0, left: 0, bottom: 0,
            width: `${Math.min(100, pct)}%`, background: utilColor(pct),
            transition: 'width .4s',
          }}
        />
        <div
          style={{
            position: 'absolute', inset: 0, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            fontSize: '13px', fontWeight: 'bold', color: '#222',
          }}
        >
          {pct.toFixed(0)}% used &middot; {free.toLocaleString()} {unit} free
        </div>
      </div>
    </div>
  );
}

export default function CapacityTab() {
  const { data, loading, error } = useServerData('slurm-capacity');

  if (loading && !data) return <div style={styles.loading}>Loading live capacity&hellip;</div>;
  if (error) return <div style={{ padding: '20px', color: 'red' }}>Error: {error}</div>;
  if (!data || !data.cluster) return <div style={styles.loading}>No capacity snapshot yet.</div>;

  const { cluster, users, updated_at } = data;

  const names = users.map((u) => u.user);
  const cpuPct = users.map((u) => (u.cpu_pct == null ? null : u.cpu_pct));
  const memPct = users.map((u) => (u.mem_pct == null ? null : u.mem_pct));
  const maxPct = Math.max(100, ...users.flatMap((u) => [u.cpu_pct || 0, u.mem_pct || 0]));

  const barData = [
    {
      type: 'bar', orientation: 'h', name: 'CPU (% of quota)',
      y: names, x: cpuPct, marker: { color: '#636EFA' },
      customdata: users.map((u) => [u.cpu_used, u.cpu_max]),
      hovertemplate:
        '<b>%{y}</b><br>CPU: %{customdata[0]} / %{customdata[1]} cores (%{x:.1f}%)<extra></extra>',
    },
    {
      type: 'bar', orientation: 'h', name: 'RAM (% of quota)',
      y: names, x: memPct, marker: { color: '#00CC96' },
      customdata: users.map((u) => [u.mem_used_gb, u.mem_max_gb]),
      hovertemplate:
        '<b>%{y}</b><br>RAM: %{customdata[0]} / %{customdata[1]} GB (%{x:.1f}%)<extra></extra>',
    },
  ];

  const barLayout = {
    barmode: 'group',
    height: Math.max(240, names.length * 72 + 90),
    margin: { t: 20, b: 50, l: 120, r: 30 },
    xaxis: { title: '% of user quota', range: [0, maxPct * 1.05], ticksuffix: '%' },
    yaxis: { automargin: true, autorange: 'reversed' },
    legend: { orientation: 'h', y: -0.18 },
    shapes: [{
      type: 'line', x0: 100, x1: 100, xref: 'x', y0: 0, y1: 1, yref: 'paper',
      line: { color: '#EF553B', width: 2, dash: 'dash' },
    }],
    annotations: [{
      x: 100, y: 1.04, xref: 'x', yref: 'paper', text: 'quota (100%)',
      showarrow: false, font: { color: '#EF553B', size: 11 }, xanchor: 'center',
    }],
  };

  return (
    <div style={styles.container}>
      <div style={styles.updated}>
        Live snapshot &middot; updated {updated_at} &middot; capacity counts only nodes currently
        accepting Slurm jobs (refreshes every 2 min)
      </div>

      <div style={styles.cards}>
        <CapacityCard
          title="CPU capacity"
          used={cluster.cpu_used}
          total={cluster.cpu_total}
          unit="cores"
          nodes={cluster.nodes_accepting}
        />
        <CapacityCard
          title="RAM capacity"
          used={cluster.mem_used_gb}
          total={cluster.mem_total_gb}
          unit="GB"
          nodes={cluster.nodes_accepting}
        />
      </div>

      <div style={styles.section}>
        <div style={styles.sectionHeader}>Users with running jobs &mdash; % of their quota</div>
        <div style={{ padding: '8px 12px' }}>
          {users.length === 0 ? (
            <div style={styles.loading}>No jobs currently running.</div>
          ) : (
            <Plot
              data={barData}
              layout={barLayout}
              useResizeHandler
              style={{ width: '100%' }}
              config={{ responsive: true, displayModeBar: false }}
            />
          )}
        </div>
      </div>

      <div style={styles.section}>
        <div style={styles.sectionHeader}>Per-user detail</div>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>User</th>
              <th style={styles.th}>CPU used</th>
              <th style={styles.th}>CPU quota</th>
              <th style={styles.th}>CPU %</th>
              <th style={styles.th}>RAM used</th>
              <th style={styles.th}>RAM quota</th>
              <th style={styles.th}>RAM %</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={u.user} style={i % 2 ? { background: '#fafafa' } : {}}>
                <td style={styles.td}><strong>{u.user}</strong></td>
                <td style={styles.td}>{u.cpu_used} cores</td>
                <td style={styles.td}>{u.cpu_max ? `${u.cpu_max} cores` : '—'}</td>
                <td style={{ ...styles.td, color: utilColor(u.cpu_pct), fontWeight: 'bold' }}>
                  {u.cpu_pct == null ? 'no limit' : `${u.cpu_pct}%`}
                </td>
                <td style={styles.td}>{u.mem_used_gb} GB</td>
                <td style={styles.td}>{u.mem_max_gb ? `${u.mem_max_gb} GB` : '—'}</td>
                <td style={{ ...styles.td, color: utilColor(u.mem_pct), fontWeight: 'bold' }}>
                  {u.mem_pct == null ? 'no limit' : `${u.mem_pct}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
