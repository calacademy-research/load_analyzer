import { useCallback, useMemo } from 'react';

const ONE_DAY_MS = 86400000;

function toDateStr(ms) {
  return new Date(ms).toISOString().split('T')[0];
}

function fromDateStr(s) {
  return new Date(s + 'T00:00:00').getTime();
}

function formatLabel(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function DateRangeSlider({ startDate, endDate, onStartChange, onEndChange, minDate }) {
  const today = useMemo(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  }, []);
  const oneYearAgo = minDate ? fromDateStr(minDate) : today - 365 * ONE_DAY_MS;

  const startVal = fromDateStr(startDate);
  const endVal = fromDateStr(endDate);

  // Clamp values to the slider range
  const startClamped = Math.max(oneYearAgo, Math.min(today, startVal));
  const endClamped = Math.max(oneYearAgo, Math.min(today, endVal));

  const startPct = ((startClamped - oneYearAgo) / (today - oneYearAgo)) * 100;
  const endPct = ((endClamped - oneYearAgo) / (today - oneYearAgo)) * 100;

  const handleStartDrag = useCallback((e) => {
    const val = Number(e.target.value);
    if (val < endClamped - ONE_DAY_MS) {
      onStartChange(toDateStr(val));
    }
  }, [endClamped, onStartChange]);

  const handleEndDrag = useCallback((e) => {
    const val = Number(e.target.value);
    if (val > startClamped + ONE_DAY_MS) {
      onEndChange(toDateStr(val));
    }
  }, [startClamped, onEndChange]);

  // Generate month tick marks
  const ticks = useMemo(() => {
    const result = [];
    const start = new Date(oneYearAgo);
    start.setDate(1);
    start.setMonth(start.getMonth() + 1);
    while (start.getTime() <= today) {
      const pct = ((start.getTime() - oneYearAgo) / (today - oneYearAgo)) * 100;
      result.push({
        pct,
        label: start.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      });
      start.setMonth(start.getMonth() + 1);
    }
    return result;
  }, [oneYearAgo, today]);

  return (
    <div style={{ padding: '4px 0 20px 0' }}>
      {/* Selected range label */}
      <div style={{ textAlign: 'center', fontSize: '15px', color: '#555', marginBottom: '4px' }}>
        {formatLabel(startDate)} — {formatLabel(endDate)}
      </div>

      {/* Slider container */}
      <div style={{ position: 'relative', height: '40px', margin: '0 10px' }}>
        {/* Track background */}
        <div style={{
          position: 'absolute', top: '16px', left: 0, right: 0, height: '8px',
          background: '#e0e0e0', borderRadius: '4px',
        }} />

        {/* Active range highlight */}
        <div style={{
          position: 'absolute', top: '16px', height: '8px',
          left: `${startPct}%`, right: `${100 - endPct}%`,
          background: '#4A90D9', borderRadius: '4px',
        }} />

        {/* Start handle */}
        <input
          type="range"
          min={oneYearAgo}
          max={today}
          step={ONE_DAY_MS}
          value={startClamped}
          onChange={handleStartDrag}
          style={{
            position: 'absolute', top: '6px', left: 0, width: '100%',
            WebkitAppearance: 'none', appearance: 'none',
            background: 'transparent', pointerEvents: 'none',
            height: '28px', margin: 0, zIndex: 3,
          }}
          className="range-thumb"
        />

        {/* End handle */}
        <input
          type="range"
          min={oneYearAgo}
          max={today}
          step={ONE_DAY_MS}
          value={endClamped}
          onChange={handleEndDrag}
          style={{
            position: 'absolute', top: '6px', left: 0, width: '100%',
            WebkitAppearance: 'none', appearance: 'none',
            background: 'transparent', pointerEvents: 'none',
            height: '28px', margin: 0, zIndex: 4,
          }}
          className="range-thumb"
        />
      </div>

      {/* Month tick labels */}
      <div style={{ position: 'relative', height: '18px', margin: '0 10px' }}>
        {ticks.map((t) => (
          <span key={t.label} style={{
            position: 'absolute', left: `${t.pct}%`, transform: 'translateX(-50%)',
            fontSize: '11px', color: '#888', whiteSpace: 'nowrap',
          }}>
            {t.label}
          </span>
        ))}
      </div>

      {/* CSS for range thumb pointer-events */}
      <style>{`
        .range-thumb::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: #4A90D9;
          border: 2px solid white;
          box-shadow: 0 1px 3px rgba(0,0,0,0.3);
          cursor: pointer;
          pointer-events: auto;
        }
        .range-thumb::-moz-range-thumb {
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: #4A90D9;
          border: 2px solid white;
          box-shadow: 0 1px 3px rgba(0,0,0,0.3);
          cursor: pointer;
          pointer-events: auto;
        }
      `}</style>
    </div>
  );
}
