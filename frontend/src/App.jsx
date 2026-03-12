import { useState, useEffect } from 'react';
import DateRangePicker from './components/DateRangePicker';
import OverviewTab from './components/OverviewTab';
import PerUserTab from './components/PerUserTab';

const styles = {
  app: { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', padding: '10px' },
  tabs: { display: 'flex', gap: '0', marginBottom: '0', borderBottom: '2px solid #ddd' },
  tab: {
    padding: '10px 24px', cursor: 'pointer', border: '1px solid #ddd',
    borderBottom: 'none', background: '#f8f8f8', borderRadius: '4px 4px 0 0',
    marginBottom: '-2px', fontSize: '14px',
  },
  activeTab: {
    padding: '10px 24px', cursor: 'pointer', border: '2px solid #ddd',
    borderBottom: '2px solid white', background: 'white', borderRadius: '4px 4px 0 0',
    marginBottom: '-2px', fontWeight: 'bold', fontSize: '14px',
  },
  loading: { textAlign: 'center', padding: '40px', color: '#888' },
};

function App() {
  const params = new URLSearchParams(window.location.search);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const fmt = (d) => d.toISOString().split('T')[0];

  const [startDate, setStartDate] = useState(params.get('start') || fmt(yesterday));
  const [endDate, setEndDate] = useState(params.get('end') || fmt(today));
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    const url = new URL(window.location);
    url.searchParams.set('start', startDate);
    url.searchParams.set('end', endDate);
    window.history.replaceState({}, '', url);
  }, [startDate, endDate]);

  return (
    <div style={styles.app}>
      <DateRangePicker
        startDate={startDate}
        endDate={endDate}
        onStartChange={setStartDate}
        onEndChange={setEndDate}
      />
      <div style={styles.tabs}>
        <div
          style={activeTab === 'overview' ? styles.activeTab : styles.tab}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </div>
        <div
          style={activeTab === 'per-user' ? styles.activeTab : styles.tab}
          onClick={() => setActiveTab('per-user')}
        >
          Per-User Breakdown
        </div>
      </div>
      {activeTab === 'overview' && <OverviewTab startDate={startDate} endDate={endDate} />}
      {activeTab === 'per-user' && <PerUserTab startDate={startDate} endDate={endDate} />}
    </div>
  );
}

export default App;
