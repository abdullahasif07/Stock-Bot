import React, { useEffect, useState } from 'react';
import { apiJson } from '../../utils/apiClient';
import '../../styles/PriceChart.css';

const W = 320;
const H = 72;
const PAD = 4;

/** Small line chart of recent daily closes, shown under price answers.
 *  Renders nothing if history can't be loaded (e.g. market-data budget used up). */
function PriceChart({ ticker }) {
  const [points, setPoints] = useState(null);

  useEffect(() => {
    let cancelled = false;
    apiJson(`/market/history/${encodeURIComponent(ticker)}`)
      .then(data => { if (!cancelled) setPoints(data.points); })
      .catch(() => { if (!cancelled) setPoints([]); });
    return () => { cancelled = true; };
  }, [ticker]);

  if (points === null) return <div className="price-chart price-chart--loading" aria-hidden="true" />;
  if (points.length < 2) return null;

  const closes = points.map(p => p.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const x = i => PAD + (i / (closes.length - 1)) * (W - 2 * PAD);
  const y = c => PAD + (1 - (c - min) / range) * (H - 2 * PAD);
  const line = closes.map((c, i) => `${x(i).toFixed(1)},${y(c).toFixed(1)}`).join(' ');
  const area = `${PAD},${H - PAD} ${line} ${W - PAD},${H - PAD}`;

  const first = closes[0];
  const last = closes[closes.length - 1];
  const change = ((last / first) - 1) * 100;
  const up = change >= 0;
  const from = points[0].date;
  const to = points[points.length - 1].date;

  return (
    <figure className={`price-chart ${up ? 'up' : 'down'}`}>
      <figcaption>
        <strong>{ticker}</strong>
        <span className="price-chart-change">{up ? '+' : ''}{change.toFixed(1)}%</span>
        <span className="price-chart-range">{points.length} trading days</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
           aria-label={`${ticker} closing price from ${from} to ${to}: ${first.toFixed(2)} to ${last.toFixed(2)}`}>
        <polygon points={area} className="price-chart-area" />
        <polyline points={line} className="price-chart-line" />
      </svg>
      <div className="price-chart-axis">
        <span>{from}</span>
        <span>Low {min.toFixed(2)} · High {max.toFixed(2)}</span>
        <span>{to}</span>
      </div>
    </figure>
  );
}

export default PriceChart;
