"""Local embeddings via fastembed (ONNX Runtime).

Replaces sentence-transformers + torch: same quality class of model
(bge-small, 384-d) at a fraction of the install size (~50 MB vs ~2 GB) and
memory, which is what makes the app fit on free-tier hosts. No API calls, so
embedding a 10-K never touches the Gemini quota.
"""
import threading

import numpy as np

from ..config import EMBEDDING_MODEL, MODEL_CACHE_DIR

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding
                print(f"[RAG] Loading embedding model {EMBEDDING_MODEL} ...")
                _model = TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=MODEL_CACHE_DIR)
    return _model


def embed_documents(texts: list[str], batch_size: int = 16) -> np.ndarray:
    vecs = np.asarray(list(_get_model().embed(texts, batch_size=batch_size)), dtype=np.float32)
    return _normalize(vecs)


def embed_query(text: str) -> np.ndarray:
    # query_embed adds the model's retrieval instruction prefix for bge models
    vec = np.asarray(list(_get_model().query_embed(text))[0], dtype=np.float32)
    return _normalize(vec[None, :])[0]


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.clip(norms, 1e-12, None)


def warmup():
    _get_model()
