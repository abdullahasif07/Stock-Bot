import hashlib
import os
import re
import tempfile

# Configure BEFORE the backend is imported (config reads env at import time).
_tmp = tempfile.mkdtemp(prefix="stockbot-test-")
os.environ.update({
    "DATA_DIR": _tmp,
    "SKIP_WARMUP": "1",
    "GEMINI_API_KEY": "test-key",
    "ALPHA_VANTAGE_API_KEY": "test-key",
    "CHAT_PER_MINUTE": "3",
    "CHAT_PER_DAY": "100",
    "TRUSTED_PROXY_HOPS": "1",
})

import numpy as np
import pytest

from backend.rag import embeddings
from backend.security import limiter


def _hash_embed(text: str, dim: int = 256) -> np.ndarray:
    """Deterministic bag-of-words embedding: offline, fast, and similar texts
    get similar vectors — good enough to test retrieval plumbing."""
    v = np.zeros(dim, dtype=np.float32)
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
    n = np.linalg.norm(v)
    return v / n if n else v


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts, batch_size=16: np.stack([_hash_embed(t) for t in texts]))
    monkeypatch.setattr(embeddings, "embed_query", _hash_embed)


@pytest.fixture(autouse=True)
def reset_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def fake_gemini(monkeypatch):
    """Replace Gemini with canned responses; records prompts."""
    from backend.utils import gemini
    calls = {"stream": [], "json": []}

    async def stream(prompt, system=None, temperature=0.3):
        calls["stream"].append(prompt)
        for part in ["Revenue grew ", "strongly [1]."]:
            yield part

    async def generate_json(prompt, system=None):
        calls["json"].append(prompt)
        return calls.get("intent", {"intent": "general_knowledge", "entity": None, "ticker": None})

    monkeypatch.setattr(gemini, "stream", stream)
    monkeypatch.setattr(gemini, "generate_json", generate_json)
    return calls
