import React, { useEffect, useState } from 'react';
import TickerSlider from '../components/Layout/TickerSlider';
import SidePanel from '../components/Layout/SidePanel';
import MarketMovers from '../components/Panels/MarketMovers';
import NewsPanel from '../components/Panels/NewsPanel';
import IpoPanel from '../components/Panels/IpoPanel';
import ChatWindow from '../components/Chat/ChatWindow';
import { apiJson } from '../utils/apiClient';
import '../styles/ChatPage.css';

function useMarketData(path, fallback) {
  const [state, setState] = useState({ data: fallback, loading: true });
  useEffect(() => {
    let cancelled = false;
    apiJson(path)
      .then(data => { if (!cancelled) setState({ data, loading: false }); })
      .catch(() => { if (!cancelled) setState(s => ({ ...s, loading: false })); });
    return () => { cancelled = true; };
  }, [path]);
  return state;
}

function ChatPage({ status, onActivity }) {
  const tickers = useMarketData('/market/tickers', []);
  const movers = useMarketData('/market/movers', { top_gainers: [], top_losers: [] });
  const news = useMarketData('/market/news', []);
  const ipos = useMarketData('/market/ipos', []);

  return (
    <>
      <TickerSlider tickerData={tickers.data} />
      <div className="main-content-wrapper">
        <SidePanel className="area-movers">
          <MarketMovers movers={movers.data} loading={movers.loading} />
        </SidePanel>

        <ChatWindow status={status} onActivity={onActivity} />

        <div className="right-column">
          <SidePanel className="area-news">
            <NewsPanel news={news.data} loading={news.loading} />
          </SidePanel>
          <SidePanel className="area-ipos">
            <IpoPanel ipos={ipos.data} loading={ipos.loading} />
          </SidePanel>
        </div>
      </div>
    </>
  );
}

export default ChatPage;
