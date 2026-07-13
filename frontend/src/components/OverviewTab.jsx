import { useState } from 'react';
import { useServerData } from '../hooks/useServerData';
import ServerChart from './ServerChart';

const SERVER_COLORS = {
  flor: '#4A90D9',
  rosalindf: '#D94A7A',
  alice: '#50B88C',
  tdobz: '#D9944A',
  'ibss-spark-1': '#7B5CB0',
};

export default function OverviewTab({ startDate, endDate }) {
  const { data, loading, error } = useServerData('overview', startDate, endDate);
  // Per-host axis mode: absolute (default, axes fixed to machine spec) vs
  // proportional (autoscale, so brief spikes above capacity stay visible).
  const [proportional, setProportional] = useState({});

  if (loading && !data) return <div style={{ padding: '40px', textAlign: 'center' }}>Loading...</div>;
  if (error) return <div style={{ padding: '20px', color: 'red' }}>Error: {error}</div>;
  if (!data) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', padding: '16px 0' }}>
      {data.servers.map((server) => {
        const color = SERVER_COLORS[server.hostname] || '#888';
        return (
          <div
            key={server.hostname}
            style={{
              borderRadius: '8px',
              overflow: 'hidden',
              border: '1px solid #ddd',
              background: '#fff',
            }}
          >
            <div
              style={{
                background: color,
                padding: '8px 16px',
                color: '#fff',
                fontSize: '15px',
                fontWeight: 'bold',
                letterSpacing: '0.3px',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {server.hostname}
              <span style={{ fontWeight: 'normal', opacity: 0.8, marginLeft: '12px', fontSize: '13px' }}>
                {server.cpu_limit} cores / {server.mem_limit} GB
              </span>
              <button
                onClick={() =>
                  setProportional((p) => ({ ...p, [server.hostname]: !p[server.hostname] }))
                }
                style={{
                  marginLeft: 'auto',
                  background: 'rgba(255,255,255,0.2)',
                  border: '1px solid rgba(255,255,255,0.6)',
                  borderRadius: '4px',
                  color: '#fff',
                  fontSize: '12px',
                  fontWeight: 'normal',
                  padding: '3px 10px',
                  cursor: 'pointer',
                }}
              >
                {proportional[server.hostname] ? 'Make absolute' : 'Make proportional'}
              </button>
            </div>
            <div style={{ padding: '4px 8px 8px' }}>
              <ServerChart server={server} proportional={!!proportional[server.hostname]} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
