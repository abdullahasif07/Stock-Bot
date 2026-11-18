import React from 'react';
import { Rocket } from 'lucide-react';
import '../../styles/IpoPanel.css';

function IpoPanel({ ipos, loading }) {
  const list = ipos ?? [];
  return (
    <div id="ipo-panel">
      <h2 className="panel-header"><Rocket size={20} /> Upcoming IPOs</h2>
      <div className="ipo-list">
        {list.length ? list.map((ipo, i) => (
          <div className="ipo-item" key={`${ipo.symbol}-${i}`} style={{ animationDelay: `${i * 0.08}s` }}>
            <div className="ipo-item-header">
              <span className="symbol">{ipo.symbol || 'N/A'}</span>
              <span className="date">{ipo.ipoDate || 'TBD'}</span>
            </div>
            <div className="name">{ipo.name || 'Unknown company'}</div>
            {(ipo.priceRange || ipo.exchange) && (
              <div className="ipo-meta">
                {[ipo.priceRange && `$${ipo.priceRange}`, ipo.exchange].filter(Boolean).join(' · ')}
              </div>
            )}
          </div>
        )) : <p className="panel-empty">{loading ? 'Loading…' : 'No IPO data available right now'}</p>}
      </div>
    </div>
  );
}

export default IpoPanel;
