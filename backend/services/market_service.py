"""Market-wide panels (ticker tape, movers, news, IPOs).

The ticker tape and movers share ONE cached TOP_GAINERS_LOSERS call, so all
panels together cost at most ~5 Alpha Vantage calls per day.
"""
import csv
import io
import re
import xml.etree.ElementTree as ET

import requests

from ..config import MARKET_CACHE_TTL, NEWS_CACHE_TTL, IPO_CACHE_TTL
from ..utils import cache
from ..utils.alpha_vantage import cached_fetch, raw_request


def _top_gainers_losers() -> dict:
    return cached_fetch({"function": "TOP_GAINERS_LOSERS"}, MARKET_CACHE_TTL) or {}


def _mover(stock: dict) -> dict:
    return {
        "ticker": stock.get("ticker", ""),
        "price": stock.get("price", "0"),
        "change_amount": stock.get("change_amount", "0"),
        "change_percentage": stock.get("change_percentage", "0%"),
    }


def _is_common_stock(ticker: str) -> bool:
    # Filter warrants/units/rights (e.g. ABCDW, XYZ+), which dominate raw movers.
    return bool(ticker) and ticker.isalpha() and len(ticker) <= 4


def get_market_movers() -> dict:
    data = _top_gainers_losers()
    pick = lambda rows: [_mover(s) for s in rows if _is_common_stock(s.get("ticker", ""))][:5]
    return {
        "top_gainers": pick(data.get("top_gainers", [])),
        "top_losers": pick(data.get("top_losers", [])),
        "last_updated": data.get("last_updated"),
    }


def get_ticker_tape() -> list[dict]:
    data = _top_gainers_losers()
    out = []
    for s in data.get("most_actively_traded", []):
        if not _is_common_stock(s.get("ticker", "")):
            continue
        out.append({
            "symbol": s["ticker"],
            "price": s.get("price", "0"),
            "change": s.get("change_amount", "0"),
            "change_percent": s.get("change_percentage", "0%"),
        })
    return out[:12]


def _news_from_alpha_vantage() -> list[dict] | None:
    data = cached_fetch({"function": "NEWS_SENTIMENT", "topics": "financial_markets", "limit": "20"},
                        NEWS_CACHE_TTL)
    feed = (data or {}).get("feed") or []
    return [
        {
            "title": a.get("title", "Untitled"),
            "url": a.get("url", "#"),
            "summary": a.get("summary", ""),
            "source": a.get("source", ""),
            "sentiment": a.get("overall_sentiment_label"),
        }
        for a in feed[:10]
    ] or None


def _news_from_rss() -> list[dict] | None:
    def fetch():
        url = "https://news.google.com/rss/search?q=stock+market+finance&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "StockBot/2.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item")[:10]:
            source = item.findtext("source") or "Google News"
            items.append({
                "title": item.findtext("title") or "Untitled",
                "url": item.findtext("link") or "#",
                "summary": f"{source} · {item.findtext('pubDate') or ''}".strip(" ·"),
                "source": source,
                "sentiment": None,
            })
        return items
    return cache.get_or_fetch("news:rss", 3600, fetch)


def get_market_news() -> list[dict]:
    return _news_from_alpha_vantage() or _news_from_rss() or []


def _fetch_ipos() -> list[dict] | None:
    resp = raw_request({"function": "IPO_CALENDAR"}, "IPO_CALENDAR")
    if resp is None or resp.text.lstrip().startswith("{"):  # JSON = error/limit payload
        return None
    rows = []
    for row in csv.DictReader(io.StringIO(resp.text)):
        # Throttled CSV responses come back as the header plus the error text split
        # one character per column — reject anything that isn't a real row.
        if row.get("symbol") and len(row.get("name") or "") > 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.get("ipoDate") or ""):
            rows.append({
                "symbol": row["symbol"],
                "name": row.get("name", ""),
                "ipoDate": row.get("ipoDate", ""),
                "priceRange": " – ".join(p for p in (row.get("priceRangeLow"), row.get("priceRangeHigh")) if p and p != "0"),
                "exchange": row.get("exchange", ""),
            })
    rows.sort(key=lambda r: r["ipoDate"])
    return rows[:10]


def get_ipo_calendar() -> list[dict]:
    return cache.get_or_fetch("av:IPO_CALENDAR", IPO_CACHE_TTL, _fetch_ipos) or []
