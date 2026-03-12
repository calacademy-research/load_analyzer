import { useServerData } from '../hooks/useServerData';
import UserStackedChart from './UserStackedChart';
import TopConsumersTable from './TopConsumersTable';

export default function PerUserTab({ startDate, endDate }) {
  const { data, loading, error } = useServerData('per-user', startDate, endDate);

  if (loading && !data) return <div style={{ padding: '40px', textAlign: 'center' }}>Loading...</div>;
  if (error) return <div style={{ padding: '20px', color: 'red' }}>Error: {error}</div>;
  if (!data) return null;

  return (
    <div>
      {data.servers.map((server) => (
        <div key={server.hostname}>
          {server.cpu_by_user && (
            <UserStackedChart
              server={server}
              dataKey="cpu_by_user"
              valueLabel="CPU load"
              yLimit={server.cpu_limit}
            />
          )}
          {server.mem_by_user && (
            <UserStackedChart
              server={server}
              dataKey="mem_by_user"
              valueLabel="Memory (GB)"
              yLimit={server.mem_limit}
            />
          )}
        </div>
      ))}
      <TopConsumersTable consumers={data.top_consumers} />
    </div>
  );
}
