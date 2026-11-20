import asyncio

import re

from fastapi import APIRouter, Depends, HTTPException

from ..security import rate_limit
from ..services import market_service, stock_service

TICKER_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$")

router = APIRouter(
    prefix="/api/market", tags=["Market Data"],
    dependencies=[Depends(rate_limit("market", per_minute=30))],
)


@router.get("/tickers")
async def ticker_tape():
    return await asyncio.to_thread(market_service.get_ticker_tape)


@router.get("/movers")
async def market_movers():
    return await asyncio.to_thread(market_service.get_market_movers)


@router.get("/news")
async def market_news():
    return await asyncio.to_thread(market_service.get_market_news)


@router.get("/ipos")
async def ipo_calendar():
    return await asyncio.to_thread(market_service.get_ipo_calendar)


@router.get("/history/{ticker}")
async def price_history(ticker: str):
    """~100 most recent daily closes, oldest first."""
    ticker = ticker.upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker.")
    points = await asyncio.to_thread(stock_service.get_price_history, ticker)
    if not points:
        raise HTTPException(status_code=404, detail="No price history available.")
    return {"ticker": ticker, "points": points}
