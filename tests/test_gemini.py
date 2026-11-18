import pytest
from google.genai import errors

from backend.utils import gemini


class FakeModels:
    def __init__(self, failures):
        self.failures = failures  # model -> HTTP code to raise
        self.calls = []

    async def generate_content(self, model, contents, config):
        self.calls.append(model)
        if model in self.failures:
            raise errors.APIError(self.failures[model], {"error": {"message": "x", "status": "X"}})
        return type("R", (), {"text": f"answer from {model}"})()


@pytest.fixture
def fake_client(monkeypatch):
    def install(failures):
        models = FakeModels(failures)
        client = type("C", (), {"aio": type("A", (), {"models": models})()})()
        monkeypatch.setattr(gemini, "get_client", lambda: client)
        monkeypatch.setattr(gemini, "GEMINI_MODEL", "primary")
        monkeypatch.setattr(gemini, "GEMINI_FALLBACK_MODELS", ["backup-1", "backup-2"])
        monkeypatch.setattr(gemini, "FINAL_RETRY_DELAY", 0)
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
