"""Single-stock data from Alpha Vantage. Every call is cached; a prediction
needs only 2 upstream calls (OVERVIEW + TIME_SERIES_DAILY) instead of 5."""
from ..config import QUOTE_CACHE_TTL, FUNDAMENTALS_CACHE_TTL
from ..utils.alpha_vantage import cached_fetch


def get_stock_quote(ticker: str) -> dict | None:
    data = cached_fetch({"function": "GLOBAL_QUOTE", "symbol": ticker}, QUOTE_CACHE_TTL)
    quote = (data or {}).get("Global Quote") or {}
    if quote.get("01. symbol", "").upper() == ticker.upper():
        return {
            "symbol": quote.get("01. symbol"),
            "open": quote.get("02. open"),
            "high": quote.get("03. high"),
            "low": quote.get("04. low"),
            "price": quote.get("05. price"),
            "volume": quote.get("06. volume"),
            "latest_trading_day": quote.get("07. latest trading day"),
            "previous_close": quote.get("08. previous close"),
            "change": quote.get("09. change"),
            "change_percent": quote.get("10. change percent"),
        }
    return None


def get_company_overview(ticker: str) -> dict | None:
    data = cached_fetch({"function": "OVERVIEW", "symbol": ticker}, FUNDAMENTALS_CACHE_TTL)
    if data and data.get("Symbol", "").upper() == ticker.upper():
        return data
    return None


def get_daily_closes(ticker: str) -> list[tuple[str, float]]:
    """Last ~100 daily closes, oldest first."""
    data = cached_fetch({"function": "TIME_SERIES_DAILY", "symbol": ticker, "outputsize": "compact"},
                        FUNDAMENTALS_CACHE_TTL / 2)
    series = (data or {}).get("Time Series (Daily)") or {}
    out = []
    for day in sorted(series):
        try:
            out.append((day, float(series[day]["4. close"])))
        except (KeyError, ValueError):
            continue
    return out


def compute_rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI."""
    if len(closes) <= period:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains += max(diff, 0)
        losses += max(-diff, 0)
    avg_gain, avg_loss = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _pct_change(closes: list[float], days: int) -> str:
    if len(closes) <= days or closes[-days - 1] == 0:
        return "N/A"
    return f"{(closes[-1] / closes[-days - 1] - 1) * 100:+.2f}%"


def get_prediction_data(ticker: str) -> dict | None:
    overview = get_company_overview(ticker)
    if not overview:
        return None
    series = get_daily_closes(ticker)
    closes = [c for _, c in series]
    rsi = compute_rsi(closes)
    return {
        "ticker": ticker,
        "company_name": overview.get("Name", ticker),
        "sector": overview.get("Sector", "N/A"),
        "market_cap": overview.get("MarketCapitalization", "N/A"),
        "pe_ratio": overview.get("PERatio", "N/A"),
        "forward_pe": overview.get("ForwardPE", "N/A"),
        "eps": overview.get("EPS", "N/A"),
        "profit_margin": overview.get("ProfitMargin", "N/A"),
        "revenue_growth_yoy": overview.get("QuarterlyRevenueGrowthYOY", "N/A"),
        "beta": overview.get("Beta", "N/A"),
        "analyst_target_price": overview.get("AnalystTargetPrice", "N/A"),
        "week_52_high": overview.get("52WeekHigh", "N/A"),
        "week_52_low": overview.get("52WeekLow", "N/A"),
        "sma_50": overview.get("50DayMovingAverage", "N/A"),
        "sma_200": overview.get("200DayMovingAverage", "N/A"),
        "last_close": f"{closes[-1]:.2f}" if closes else "N/A",
        "last_close_date": series[-1][0] if series else "N/A",
        "rsi_14": rsi if rsi is not None else "N/A",
        "return_1m": _pct_change(closes, 21),
        "return_3m": _pct_change(closes, 63),
    }


def search_ticker_symbols(keywords: str) -> list[dict]:
    """Alpha Vantage symbol search (used only when SEC lookup finds nothing)."""
    data = cached_fetch({"function": "SYMBOL_SEARCH", "keywords": keywords.strip().lower()}, 7 * 86400)
    matches = (data or {}).get("bestMatches") or []
    return [
        {"symbol": m.get("1. symbol"), "name": m.get("2. name")}
        for m in matches[:5]
        if m.get("4. region") == "United States"
    ]
