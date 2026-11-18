import pytest
from google.genai import errors

from backend.utils import gemini


class FakeModels:
    def __init__(self, failures, rejects_thinking=()):
        self.failures = failures  # model -> HTTP code to raise
        self.rejects_thinking = set(rejects_thinking)
        self.calls = []
        self.configs = []

    async def generate_content(self, model, contents, config):
        self.calls.append(model)
        self.configs.append(config)
        if model in self.rejects_thinking and config.thinking_config is not None:
            raise errors.APIError(400, {"error": {"message": "thinking_level is not supported", "status": "INVALID_ARGUMENT"}})
        if model in self.failures:
            raise errors.APIError(self.failures[model], {"error": {"message": "x", "status": "X"}})
        return type("R", (), {"text": f"answer from {model}"})()


@pytest.fixture
def fake_client(monkeypatch):
    def install(failures, **kw):
        models = FakeModels(failures, **kw)
        client = type("C", (), {"aio": type("A", (), {"models": models})()})()
        monkeypatch.setattr(gemini, "get_client", lambda: client)
        monkeypatch.setattr(gemini, "GEMINI_MODEL", "primary")
        monkeypatch.setattr(gemini, "GEMINI_FALLBACK_MODELS", ["backup-1", "backup-2"])
        monkeypatch.setattr(gemini, "FINAL_RETRY_DELAY", 0)
        monkeypatch.setattr(gemini, "FALLBACK_DELAY", 0)
        monkeypatch.setattr(gemini, "GEMINI_THINKING_LEVEL", "MINIMAL")
        monkeypatch.setattr(gemini, "_cooldown_until", {})
        monkeypatch.setattr(gemini, "_thinking_for", {})
        return models
    return install


@pytest.mark.anyio
async def test_falls_back_when_primary_overloaded_or_retired(fake_client):
    models = fake_client({"primary": 503, "backup-1": 404})
    assert await gemini.generate("hi") == "answer from backup-2"
    assert models.calls == ["primary", "backup-1", "backup-2"]


@pytest.mark.anyio
async def test_non_transient_error_is_raised_immediately(fake_client):
    models = fake_client({"primary": 400})
    with pytest.raises(errors.APIError):
        await gemini.generate("hi")
    assert models.calls == ["primary"]


@pytest.mark.anyio
async def test_failed_model_is_skipped_on_next_request(fake_client):
    models = fake_client({"primary": 503})
    await gemini.generate("hi")
    models.calls.clear()
    assert await gemini.generate("again") == "answer from backup-1"
    assert models.calls == ["backup-1"]  # primary is cooling down


@pytest.mark.anyio
async def test_preferred_model_is_tried_first(fake_client):
    models = fake_client({})
    assert await gemini.generate("hi", model="fast") == "answer from fast"
    assert models.calls == ["fast"]


@pytest.mark.anyio
async def test_thinking_level_sent_and_dropped_if_rejected(fake_client):
    models = fake_client({}, rejects_thinking={"primary"})
    assert await gemini.generate("hi") == "answer from primary"
    assert models.calls == ["primary", "primary", "primary"]
    levels = [c.thinking_config and c.thinking_config.thinking_level for c in models.configs]
    assert [getattr(lv, "value", lv) for lv in levels] == ["MINIMAL", "LOW", None]


@pytest.mark.anyio
async def test_stalled_model_falls_back(fake_client, monkeypatch):
    import asyncio
    models = fake_client({})
    real = models.generate_content

    async def slow(model, contents, config):
        if model == "primary":
            await asyncio.sleep(5)
        return await real(model, contents, config)
    models.generate_content = slow
    monkeypatch.setattr(gemini, "GENERATE_TIMEOUT", 0.05)
    assert await gemini.generate("hi") == "answer from backup-1"
