import React from 'react';
import { Newspaper } from 'lucide-react';
import { safeUrl } from '../../utils/format';
import '../../styles/NewsPanel.css';

function NewsPanel({ news, loading }) {
  const articles = (news ?? []).slice(0, 10);
  return (
    <div id="news-panel">
      <h2 className="panel-header"><Newspaper size={20} /> Latest News</h2>
      <div className="news-list">
        {articles.length ? articles.map((a, i) => (
          <a href={safeUrl(a.url)} target="_blank" rel="noopener noreferrer" className="news-item"
             key={a.url || i} style={{ animationDelay: `${i * 0.08}s` }}>
            <div className="news-item-title">{a.title}</div>
            <div className="news-item-summary">
              {a.sentiment && (
                <span className={`sentiment ${a.sentiment.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{a.sentiment}</span>
              )}
              {a.source}
            </div>
          </a>
        )) : <p className="panel-empty">{loading ? 'Loading…' : 'No news available right now'}</p>}
      </div>
    </div>
  );
}

export default NewsPanel;
