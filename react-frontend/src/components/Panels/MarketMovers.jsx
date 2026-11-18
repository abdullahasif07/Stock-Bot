import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { toNumber } from '../../utils/format';
import '../../styles/MarketMovers.css';

function MoverItem({ stock, type }) {
  const positive = type === 'gainer';
  const sign = positive ? '+' : '';
  return (
    <div className={`mover-item ${type}`}>
      <div className="mover-item-header">
        <span className="symbol">{stock.ticker}</span>
        <span className="price">${toNumber(stock.price).toFixed(2)}</span>
      </div>
      <div className="mover-item-details">
        <span className={`change ${positive ? 'positive' : 'negative'}`}>{sign}{toNumber(stock.change_amount).toFixed(2)}</span>
        <span className={`change ${positive ? 'positive' : 'negative'}`}>{sign}{toNumber(stock.change_percentage).toFixed(2)}%</span>
      </div>
    </div>
  );
}

function MarketMovers({ movers, loading }) {
  const gainers = movers?.top_gainers ?? [];
  const losers = movers?.top_losers ?? [];
  const empty = (label) => <p className="panel-empty">{loading ? 'Loading…' : `No ${label} data right now`}</p>;

  return (
    <div>
      <h2 className="panel-header"><TrendingUp size={20} /> Top Gainers</h2>
      <div className="movers-list">
        {gainers.length ? gainers.map(s => <MoverItem key={s.ticker} stock={s} type="gainer" />) : empty('gainers')}
      </div>
      <h2 className="panel-header" style={{ marginTop: '1.25rem' }}><TrendingDown size={20} /> Top Losers</h2>
      <div className="movers-list">
        {losers.length ? losers.map(s => <MoverItem key={s.ticker} stock={s} type="loser" />) : empty('losers')}
      </div>
      {movers?.last_updated && <p className="panel-footnote">Updated {movers.last_updated}</p>}
    </div>
  );
}

export default MarketMovers;
