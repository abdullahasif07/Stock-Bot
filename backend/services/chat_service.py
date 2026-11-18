"""Chat orchestration. Stateless: the browser keeps the conversation and sends
the last few messages with each request.

LLM cost per message: 1 intent call + 1 streamed answer (previously up to
5 calls: intent twice, history summarisation twice, plus the answer)."""
import asyncio
import json
import re
from typing import AsyncIterator

from ..config import GEMINI_FAST_MODEL
from ..constants import MSG_CLARIFICATION, MSG_NEED_STOCK_NAME, MSG_NO_PRICE_DATA, MSG_NO_PREDICTION_DATA
from ..prompts import gemini as prompts
from ..utils import gemini
from . import sec_service, stock_service

TICKER_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$")
STOCK_INTENTS = {"get_specific_data", "get_prediction_or_advice"}


async def _single(text: str) -> AsyncIterator[str]:
    yield text


async def resolve_ticker(entity: str | None, ticker_guess: str | None) -> tuple[str | None, list[dict]]:
    """Return (ticker, clarification_choices). Uses the free SEC directory first
    and only falls back to Alpha Vantage search when SEC has no match."""
    # The LLM's own guess (e.g. Google -> GOOGL), or an uppercase ticker the user typed.
    for candidate in (ticker_guess, entity if entity and entity.isupper() else None):
        if candidate and TICKER_RE.match(candidate.strip().upper()):
            if await asyncio.to_thread(sec_service.lookup_ticker, candidate):
                return candidate.strip().upper(), []
    if not entity:
        return None, []
    confident, candidates = await asyncio.to_thread(sec_service.resolve_company, entity)
    if confident:
        return confident["ticker"], []
    if len(candidates) > 1:
        return None, [{"symbol": c["ticker"], "name": c["name"]} for c in candidates]
    av = await asyncio.to_thread(stock_service.search_ticker_symbols, entity)
    if len(av) == 1:
        return av[0]["symbol"], []
    return None, av


async def handle_message(message: str, history: list[dict], context: dict):
    """Returns ("clarification", dict) or ("stream", async iterator)."""
    history_text = gemini.format_history(history)

    if context.get("awaiting_clarification"):
        intent = context.get("original_intent", "get_specific_data")
        ticker = message.strip().upper()
        if not TICKER_RE.match(ticker):
            return "stream", _single("Please pick one of the suggested tickers.")
        return "stream", _stock_answer(intent, ticker, ticker, message)

    intent_data = await gemini.generate_json(prompts.intent_classification(history_text, message),
                                             model=GEMINI_FAST_MODEL)
    intent = intent_data.get("intent") or "general_knowledge"
    entity = intent_data.get("entity")

    if intent in STOCK_INTENTS:
        if not entity and not intent_data.get("ticker"):
            return "stream", _single(MSG_NEED_STOCK_NAME)
        ticker, choices = await resolve_ticker(entity, intent_data.get("ticker"))
        if not ticker and choices:
            return "clarification", {
                "response_type": "clarification",
                "message": MSG_CLARIFICATION.format(entity=entity),
                "choices": choices,
                "original_intent": intent,
            }
        if not ticker:
            return "stream", _single(f"I couldn't find a US-listed ticker for \"{entity}\".")
        return "stream", _stock_answer(intent, ticker, entity or ticker, message)

    return "stream", gemini.stream(prompts.general_response(history_text, message),
                                   system=prompts.ASSISTANT_SYSTEM, temperature=0.5)


async def _stock_answer(intent: str, ticker: str, label: str, message: str) -> AsyncIterator[str]:
    if intent == "get_prediction_or_advice":
        data = await asyncio.to_thread(stock_service.get_prediction_data, ticker)
        if not data:
            yield MSG_NO_PREDICTION_DATA.format(ticker=ticker)
            return
        async for chunk in gemini.stream(prompts.prediction_analysis(data, message), temperature=0.4):
            yield chunk
        return

    quote = await asyncio.to_thread(stock_service.get_stock_quote, ticker)
    if not quote:
        yield MSG_NO_PRICE_DATA.format(ticker=ticker)
        return
    async for chunk in gemini.stream(prompts.quote_response(f"{label} ({ticker})", json.dumps(quote))):
        yield chunk
