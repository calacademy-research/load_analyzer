const styles = {
  container: { display: 'flex', alignItems: 'center', gap: '10px', margin: '10px 0' },
  input: { padding: '6px 10px', fontSize: '14px', border: '1px solid #ccc', borderRadius: '4px' },
};

export default function DateRangePicker({ startDate, endDate, onStartChange, onEndChange }) {
  return (
    <div style={styles.container}>
      <input
        type="date"
        value={startDate}
        onChange={(e) => onStartChange(e.target.value)}
        style={styles.input}
      />
      <span>to</span>
      <input
        type="date"
        value={endDate}
        onChange={(e) => onEndChange(e.target.value)}
        style={styles.input}
      />
    </div>
  );
}
