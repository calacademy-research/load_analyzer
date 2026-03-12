import { useState, useMemo } from 'react';

const styles = {
  container: { margin: '10px' },
  h3: { margin: '10px 0' },
  filterInput: {
    padding: '6px 10px', fontSize: '14px', border: '1px solid #ccc',
    borderRadius: '4px', marginBottom: '8px', width: '250px',
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '14px' },
  th: {
    textAlign: 'left', padding: '8px', fontWeight: 'bold',
    backgroundColor: '#f0f0f0', cursor: 'pointer', userSelect: 'none',
    borderBottom: '2px solid #ddd',
  },
  td: { textAlign: 'left', padding: '8px', borderBottom: '1px solid #eee' },
  oddRow: { backgroundColor: '#fafafa' },
};

const COLUMNS = [
  { key: 'server', label: 'Server' },
  { key: 'user', label: 'User' },
  { key: 'avg_cpu', label: 'Avg CPU' },
  { key: 'peak_cpu', label: 'Peak CPU' },
  { key: 'avg_mem', label: 'Avg Mem (GB)' },
  { key: 'peak_mem', label: 'Peak Mem (GB)' },
];

export default function TopConsumersTable({ consumers }) {
  const [sortCol, setSortCol] = useState('peak_cpu');
  const [sortAsc, setSortAsc] = useState(false);
  const [filter, setFilter] = useState('');

  const sorted = useMemo(() => {
    let rows = [...consumers];
    if (filter) {
      const f = filter.toLowerCase();
      rows = rows.filter(
        (r) => r.server.toLowerCase().includes(f) || r.user.toLowerCase().includes(f),
      );
    }
    rows.sort((a, b) => {
      const av = a[sortCol] ?? -Infinity;
      const bv = b[sortCol] ?? -Infinity;
      if (av < bv) return sortAsc ? -1 : 1;
      if (av > bv) return sortAsc ? 1 : -1;
      return 0;
    });
    return rows;
  }, [consumers, sortCol, sortAsc, filter]);

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(false);
    }
  };

  const arrow = (col) => (sortCol === col ? (sortAsc ? ' \u25B2' : ' \u25BC') : '');

  return (
    <div style={styles.container}>
      <h3 style={styles.h3}>Top Consumers</h3>
      <input
        type="text"
        placeholder="Filter by server or user..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={styles.filterInput}
      />
      <table style={styles.table}>
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th key={col.key} style={styles.th} onClick={() => handleSort(col.key)}>
                {col.label}{arrow(col.key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, 20).map((row, i) => (
            <tr key={`${row.server}-${row.user}`} style={i % 2 === 1 ? styles.oddRow : undefined}>
              {COLUMNS.map((col) => (
                <td key={col.key} style={styles.td}>
                  {row[col.key] != null ? row[col.key] : '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
