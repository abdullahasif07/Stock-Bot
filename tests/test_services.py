import pytest

from backend.services import sec_service, stock_service, chat_service
from backend.utils.quota import DailyBudget

COMPANIES = [
    {"cik": 320193, "ticker": "AAPL", "name": "Apple Inc."},
    {"cik": 1418121, "ticker": "APLE", "name": "Apple Hospitality REIT, Inc."},
    {"cik": 789019, "ticker": "MSFT", "name": "MICROSOFT CORP"},
    {"cik": 19617, "ticker": "JPM", "name": "JPMORGAN CHASE & CO"},
    {"cik": 1652044, "ticker": "GOOGL", "name": "Alphabet Inc."},
    {"cik": 1652044, "ticker": "GOOG", "name": "Alphabet Inc."},
]


@pytest.fixture(autouse=True)
def fake_sec(monkeypatch):
    monkeypatch.setattr(sec_service, "_load_companies", lambda: COMPANIES)
    monkeypatch.setattr(sec_service, "_by_ticker", None)


def test_normalize_name():
    assert sec_service.normalize_name("JPMORGAN CHASE & CO") == "jpmorgan chase"
    assert sec_service.normalize_name("Apple Inc.") == "apple"


@pytest.mark.parametrize("query,expected", [
    ("apple", "AAPL"), ("AAPL", "AAPL"), ("Microsoft", "MSFT"), ("jpmorgan", "JPM"),
    ("google", "GOOGL"), ("apple hospitality", "APLE"),
])
def test_resolve_company(query, expected):
    match, _ = sec_service.resolve_company(query)
    assert match and match["ticker"] == expected


def test_resolve_company_unknown():
    assert sec_service.resolve_company("zzzz nothing") == (None, [])


def test_html_to_text_strips_xbrl_and_flattens_tables():
    html = b"""<html><body>
      <div style="display:none"><ix:header>hidden metadata</ix:header></div>
      <p>Item 7. Management's Discussion</p>
      <table><tr><td>Net sales</td><td>$</td><td>574,785</td></tr></table>
      <p>Table of Contents</p><p>42</p>
    </body></html>"""
    text = sec_service.html_to_text(html)
    assert "hidden metadata" not in text
    assert "Net sales | 574,785" in text
    assert "Table of Contents" not in text and "\n42" not in text


def test_compute_rsi():
    assert stock_service.compute_rsi([1.0] * 5) is None
    assert stock_service.compute_rsi([float(i) for i in range(1, 30)]) == 100.0
    zigzag = [10 + (i % 2) for i in range(40)]
    assert 40 < stock_service.compute_rsi(zigzag) < 60


def test_daily_budget(tmp_path, monkeypatch):
    b = DailyBudget("unit", 2)
    assert b.try_consume() and b.try_consume()
    assert not b.try_consume()
    assert b.remaining() == 0
    b._day = "2000-01-01"  # simulate a new UTC day
    assert b.remaining() == 2


@pytest.mark.anyio
async def test_resolve_ticker_prefers_llm_guess_then_sec(monkeypatch):
    av_calls = []
    monkeypatch.setattr(stock_service, "search_ticker_symbols", lambda q: av_calls.append(q) or [])
    assert await chat_service.resolve_ticker("Google", "GOOGL") == ("GOOGL", [])
    assert await chat_service.resolve_ticker("Microsoft", None) == ("MSFT", [])
    assert await chat_service.resolve_ticker("MSFT", None) == ("MSFT", [])
    assert av_calls == []  # never spent Alpha Vantage quota


def test_ipo_parser_rejects_throttled_garbage(monkeypatch):
    from backend.services import market_service
    good = "symbol,name,ipoDate,priceRangeLow,priceRangeHigh,currency,exchange\r\nXYZ,Foo Corp,2026-11-20,10,12,USD,NYSE\r\n"
    garbage = "symbol,name,ipoDate,priceRangeLow,priceRangeHigh,currency,exchange\r\nI,n,f,o,r,m,a,t,i,o,n\r\n"
    monkeypatch.setattr(market_service, "raw_request", lambda p, l: type("R", (), {"text": good + garbage.split("\r\n", 1)[1]}))
    rows = market_service._fetch_ipos()
    assert [r["symbol"] for r in rows] == ["XYZ"]
    assert rows[0]["priceRange"] == "10 – 12"


def test_premium_endpoint_is_remembered_and_skipped(monkeypatch):
    from backend.utils import alpha_vantage
    calls = []

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"Information": "Thank you! This is a premium endpoint. Subscribe..."}

    monkeypatch.setattr(alpha_vantage.requests, "get", lambda *a, **k: calls.append(1) or Resp())
    monkeypatch.setattr(alpha_vantage, "MIN_INTERVAL", 0)
    assert alpha_vantage.fetch({"function": "PREMIUM_ONLY_TEST"}) is None
    assert alpha_vantage.fetch({"function": "PREMIUM_ONLY_TEST"}) is None
    assert len(calls) == 1  # second call never left the server


def test_daily_limit_note_does_not_mark_premium(monkeypatch):
    from backend.utils import alpha_vantage
    calls = []

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"Information": "Our standard API rate limit is 25 requests per day. "
                                               "Please subscribe to any of the premium plans."}

    monkeypatch.setattr(alpha_vantage.requests, "get", lambda *a, **k: calls.append(1) or Resp())
    monkeypatch.setattr(alpha_vantage, "MIN_INTERVAL", 0)
    alpha_vantage.fetch({"function": "LIMITED_TEST"})
    alpha_vantage.fetch({"function": "LIMITED_TEST"})
    assert len(calls) == 2


def test_failed_fetch_backs_off_and_serves_stale():
    from backend.utils import cache
    calls = []
    assert cache.get_or_fetch("backoff-test", 0, lambda: calls.append(1) or None) is None
    assert cache.get_or_fetch("backoff-test", 0, lambda: calls.append(1) or "x") is None
    assert len(calls) == 1  # second request didn't hit upstream during backoff
