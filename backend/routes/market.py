import asyncio

from fastapi import APIRouter, Depends

from ..security import rate_limit
from ..services import market_service

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
