"""Prompt templates for the general chat assistant."""

from ..constants import PREDICTION_DISCLAIMER, FINANCIAL_DISCLAIMER

ASSISTANT_SYSTEM = f"""You are StockBot, a concise, friendly financial assistant. \
Explain clearly using markdown. You do not have live data unless it is provided in the prompt; \
if asked for real-time figures you weren't given, say so. \
If you give anything resembling investment advice, end with: "{FINANCIAL_DISCLAIMER}" """


def intent_classification(history_text: str, user_prompt: str) -> str:
    return f"""Classify the user's LATEST message for a stock-market assistant.

INTENTS:
- "get_specific_data": wants CURRENT market data (price, change, volume, open/close) for one company.
- "get_prediction_or_advice": wants a forecast, outlook, valuation opinion, or buy/sell/hold view on one company.
- "get_qualitative_analysis": wants an explanation of past events, business model, trends, or comparisons.
- "general_knowledge": general finance concepts, greetings, or anything else.

Return JSON: {{"intent": <one of the above>, "entity": <company name or ticker the user refers to, \
resolving pronouns from the conversation, or null>, "ticker": <the primary US ticker for that entity \
if you are confident, e.g. "GOOGL" for Google, else null>}}

RECENT CONVERSATION:
{history_text or "(none)"}

LATEST MESSAGE: "{user_prompt}"
"""


def prediction_analysis(data: dict, user_prompt: str) -> str:
    rows = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in data.items())
    return f"""The user asked: "{user_prompt}"

Recently fetched market data (Alpha Vantage):
{rows}

Write a balanced outlook using ONLY this data: valuation (P/E vs growth/margins), trend \
(price vs 50/200-day averages, 1m/3m returns), momentum (RSI-14: >70 overbought, <30 oversold), \
and the analyst target vs last close. Give a short bull case, bear case, and an overall stance \
(bullish/neutral/bearish) with a confidence level. Use markdown headings and bullets. \
End with: "{PREDICTION_DISCLAIMER}" """


def quote_response(company: str, quote_json: str) -> str:
    return (
        f"The user asked about {company}. Using ONLY this Alpha Vantage quote, give a short, friendly "
        f"summary starting with \"Based on the latest data\", including price, daily change, the day's "
        f"range, volume and the trading day. Use a compact markdown table.\nQuote: {quote_json}"
    )


def general_response(history_text: str, user_prompt: str) -> str:
    history_block = f"RECENT CONVERSATION:\n{history_text}\n\n" if history_text else ""
    return f"{history_block}USER: {user_prompt}"
