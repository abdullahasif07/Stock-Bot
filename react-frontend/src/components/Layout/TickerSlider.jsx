import React from 'react';
import { toNumber } from '../../utils/format';
import '../../styles/TickerSlider.css';

function TickerItem({ stock }) {
  const change = toNumber(stock.change);
  const pct = toNumber(stock.change_percent);
  const sign = change >= 0 ? '+' : '';
  return (
    <div className="ticker-item">
      <span className="symbol">{stock.symbol}</span>
      <span className="price">${toNumber(stock.price).toFixed(2)}</span>
      <span className={`change ${change >= 0 ? 'positive' : 'negative'}`}>
        {sign}{change.toFixed(2)} ({sign}{pct.toFixed(2)}%)
      </span>
    </div>
  );
}

function TickerSlider({ tickerData }) {
  const items = tickerData ?? [];
  // Rendered twice so the CSS marquee loops seamlessly.
  const doubled = items.concat(items);
  return (
    <div className="ticker-slider-container" aria-label="Most actively traded stocks">
      <div className="ticker-track">
        {doubled.map((stock, i) => <TickerItem key={`${stock.symbol}-${i}`} stock={stock} />)}
      </div>
    </div>
  );
}

export default TickerSlider;
