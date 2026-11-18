"""Gemini access via the current `google-genai` SDK (the old
`google-generativeai` package is deprecated). All calls are async, count
against the global daily budget once per user request, time out instead of
hanging, and fall back to other models when one is overloaded (429/503) or
retired (404) — Google's free tier hits "high demand" spikes regularly."""
import asyncio
import json
from typing import AsyncIterator

from google import genai
from google.genai import errors, types

from ..config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS
from .quota import gemini_budget

_client: genai.Client | None = None
REQUEST_TIMEOUT_MS = 60_000
FINAL_RETRY_DELAY = 3  # seconds before one last try of the primary model


class GeminiUnavailable(Exception):
    pass


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise GeminiUnavailable("GEMINI_API_KEY is not configured on the server.")
        _client = genai.Client(api_key=GEMINI_API_KEY,
                               http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    return _client


def _config(system: str | None, temperature: float, json_mode: bool, max_tokens: int | None):
    cfg = dict(temperature=temperature, system_instruction=system)
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    if max_tokens:
        cfg["max_output_tokens"] = max_tokens
    return types.GenerateContentConfig(**cfg)


def _attempts() -> list[tuple[str, float]]:
    """(model, delay-before) schedule: primary, each fallback, then primary again."""
    models = list(dict.fromkeys([GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]))
    return [(m, 0.0 if i == 0 else 0.5) for i, m in enumerate(models)] + [(models[0], FINAL_RETRY_DELAY)]


def _should_fall_back(e: errors.APIError) -> bool:
    return getattr(e, "code", None) in (404, 429, 500, 503, 504)


async def generate(prompt: str, *, system: str | None = None, temperature: float = 0.3,
                   json_mode: bool = False, max_tokens: int | None = None) -> str:
    client = get_client()
    gemini_budget.consume()
    attempts = _attempts()
    for i, (model, delay) in enumerate(attempts):
        if delay:
            await asyncio.sleep(delay)
        try:
            resp = await client.aio.models.generate_content(
                model=model, contents=prompt,
                config=_config(system, temperature, json_mode, max_tokens),
            )
            return resp.text or ""
        except errors.APIError as e:
            if not _should_fall_back(e) or i == len(attempts) - 1:
                raise
            print(f"[GEMINI] {model} -> {e.code}; trying {attempts[i + 1][0]}")


async def generate_json(prompt: str, *, system: str | None = None) -> dict:
    text = await generate(prompt, system=system, temperature=0.0, json_mode=True)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


async def stream(prompt: str, *, system: str | None = None, temperature: float = 0.3) -> AsyncIterator[str]:
    """Yield text chunks. Falls back to another model only if nothing has been streamed yet."""
    client = get_client()
    gemini_budget.consume()
    attempts = _attempts()
    for i, (model, delay) in enumerate(attempts):
        if delay:
            await asyncio.sleep(delay)
        started = False
        try:
            response = await client.aio.models.generate_content_stream(
                model=model, contents=prompt,
                config=_config(system, temperature, False, None),
            )
            async for chunk in response:
                if chunk.text:
                    started = True
                    yield chunk.text
            return
        except errors.APIError as e:
            if started or not _should_fall_back(e) or i == len(attempts) - 1:
                raise
            print(f"[GEMINI] {model} -> {e.code}; trying {attempts[i + 1][0]}")


def format_history(history: list[dict], max_chars: int = 1500) -> str:
    lines = []
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        text = (msg.get("text") or "").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + " …"
        lines.append(f"{role}: {text}")
    return "\n".join(lines)
