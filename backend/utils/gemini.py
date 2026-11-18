"""Gemini access via the current `google-genai` SDK (the old
`google-generativeai` package is deprecated). All calls are async, count
against the global daily budget once per user request, time out instead of
hanging, and fall back to other models when one is overloaded (429/503) or
retired (404) — Google's free tier hits "high demand" spikes regularly.

Latency notes:
- Thinking is set to GEMINI_THINKING_LEVEL (default "minimal"); Gemini 3's
  default deep thinking adds seconds before the first token.
- A model that just failed is put on cooldown and skipped, so one overloaded
  model doesn't make every request wait for it to fail first.
- Overloaded models sometimes stall ~45s before returning 503. If a model
  hasn't produced anything within FIRST_TOKEN_TIMEOUT, we give up on it and
  fall back (except on the last attempt, which gets the full timeout)."""
import asyncio
import json
import time
from typing import AsyncIterator

from google import genai
from google.genai import errors, types

from ..config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS, GEMINI_THINKING_LEVEL
from .quota import gemini_budget

_client: genai.Client | None = None
REQUEST_TIMEOUT_MS = 60_000
FINAL_RETRY_DELAY = 3       # seconds before one last try of the best model
FALLBACK_DELAY = 0.3
TRANSIENT_COOLDOWN = 120    # skip a model for this long after a 429/5xx
RETIRED_COOLDOWN = 24 * 3600
FIRST_TOKEN_TIMEOUT = 12    # seconds; streaming: until the first chunk
GENERATE_TIMEOUT = 20       # seconds; non-streamed calls (short JSON answers)

_cooldown_until: dict[str, float] = {}
# Per-model thinking level after a rejection (MINIMAL -> LOW -> None = model default).
_thinking_for: dict[str, str | None] = {}
_THINKING_STEP_DOWN = {"MINIMAL": "LOW"}


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


def _config(model: str, system: str | None, temperature: float, json_mode: bool,
            max_tokens: int | None):
    cfg = dict(temperature=temperature, system_instruction=system)
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    if max_tokens:
        cfg["max_output_tokens"] = max_tokens
    level = _thinking_for.get(model, GEMINI_THINKING_LEVEL)
    if level:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level=level)
    return types.GenerateContentConfig(**cfg)


def _attempts(prefer: str | None = None) -> list[tuple[str, float]]:
    """(model, delay-before) schedule over models not on cooldown, then one
    last try of the first. If every model is cooling down, try them all anyway."""
    models = list(dict.fromkeys(m for m in (prefer, GEMINI_MODEL, *GEMINI_FALLBACK_MODELS) if m))
    now = time.monotonic()
    healthy = [m for m in models if _cooldown_until.get(m, 0) <= now] or models
    schedule = [(m, 0.0 if i == 0 else FALLBACK_DELAY) for i, m in enumerate(healthy)]
    return schedule + [(healthy[0], FINAL_RETRY_DELAY)]


def _should_fall_back(e: errors.APIError) -> bool:
    return getattr(e, "code", None) in (404, 429, 500, 503, 504)


def _thinking_rejected(e: errors.APIError, model: str) -> bool:
    """Some models don't accept every thinking level (400). Step down and retry."""
    level = _thinking_for.get(model, GEMINI_THINKING_LEVEL)
    if getattr(e, "code", None) == 400 and level and "thinking" in str(e).lower():
        _thinking_for[model] = _THINKING_STEP_DOWN.get(level)
        print(f"[GEMINI] {model} rejected thinking_level={level}; retrying with {_thinking_for[model] or 'default'}")
        return True
    return False


class _Stalled(Exception):
    code = 504


def _mark_failed(model: str, code) -> None:
    _cooldown_until[model] = time.monotonic() + (RETIRED_COOLDOWN if code == 404 else TRANSIENT_COOLDOWN)


async def generate(prompt: str, *, system: str | None = None, temperature: float = 0.3,
                   json_mode: bool = False, max_tokens: int | None = None,
                   model: str | None = None) -> str:
    """`model` is tried first; the configured chain is the fallback."""
    client = get_client()
    gemini_budget.consume()
    attempts = _attempts(model)
    i = 0
    while i < len(attempts):
        name, delay = attempts[i]
        if delay:
            await asyncio.sleep(delay)
        t0 = time.monotonic()
        last = i == len(attempts) - 1
        try:
            call = client.aio.models.generate_content(
                model=name, contents=prompt,
                config=_config(name, system, temperature, json_mode, max_tokens),
            )
            try:
                resp = await (call if last else asyncio.wait_for(call, GENERATE_TIMEOUT))
            except asyncio.TimeoutError:
                raise _Stalled() from None
            _cooldown_until.pop(name, None)
            print(f"[GEMINI] {name} answered in {time.monotonic() - t0:.1f}s")
            return resp.text or ""
        except (errors.APIError, _Stalled) as e:
            if isinstance(e, errors.APIError) and _thinking_rejected(e, name):
                attempts[i] = (name, 0.0)
                continue
            if isinstance(e, errors.APIError) and (not _should_fall_back(e) or last):
                raise
            _mark_failed(name, e.code)
            print(f"[GEMINI] {name} -> {e.code} after {time.monotonic() - t0:.1f}s; trying {attempts[i + 1][0]}")
            i += 1


async def generate_json(prompt: str, *, system: str | None = None, model: str | None = None) -> dict:
    text = await generate(prompt, system=system, temperature=0.0, json_mode=True, model=model)
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
    i = 0
    while i < len(attempts):
        name, delay = attempts[i]
        if delay:
            await asyncio.sleep(delay)
        started = False
        t0 = time.monotonic()
        last = i == len(attempts) - 1
        try:
            try:
                first = asyncio.ensure_future(_open_stream(client, name, prompt, system, temperature))
                it, chunk = await (first if last else asyncio.wait_for(first, FIRST_TOKEN_TIMEOUT))
            except asyncio.TimeoutError:
                raise _Stalled() from None
            while chunk is not None:
                if chunk.text:
                    if not started:
                        print(f"[GEMINI] {name} first token in {time.monotonic() - t0:.1f}s")
                    started = True
                    yield chunk.text
                chunk = await anext(it, None)
            _cooldown_until.pop(name, None)
            return
        except (errors.APIError, _Stalled) as e:
            if started:
                raise
            if isinstance(e, errors.APIError) and _thinking_rejected(e, name):
                attempts[i] = (name, 0.0)
                continue
            if isinstance(e, errors.APIError) and (not _should_fall_back(e) or last):
                raise
            _mark_failed(name, e.code)
            print(f"[GEMINI] {name} -> {e.code} after {time.monotonic() - t0:.1f}s; trying {attempts[i + 1][0]}")
            i += 1


async def _open_stream(client, name, prompt, system, temperature):
    """Start a stream and wait for its first non-empty chunk (or the end)."""
    response = await client.aio.models.generate_content_stream(
        model=name, contents=prompt, config=_config(name, system, temperature, False, None))
    it = aiter(response)
    async for chunk in it:
        if chunk.text:
            return it, chunk
    return it, None


def format_history(history: list[dict], max_chars: int = 1500) -> str:
    lines = []
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        text = (msg.get("text") or "").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + " …"
        lines.append(f"{role}: {text}")
    return "\n".join(lines)
