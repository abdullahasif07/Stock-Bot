"""Hybrid (BM25 + dense) retrieval index with on-disk persistence.

Financial questions mix semantics ("how is the cloud business doing") with
exact tokens ("AWS operating income 2024", "Item 1A"). Dense vectors handle
the first, BM25 the second; results are merged with Reciprocal Rank Fusion.
For a single filing (~300-600 chunks) brute-force numpy search takes well
under a millisecond, so no FAISS dependency is needed.
"""
import json
import os
import re
from dataclasses import dataclass, field

import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import Chunk
from . import embeddings

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
_STOP = set("the a an and or of to in for on with by as is are was were be been at from that this "
            "it its our we us which what how who whom does do did has have had not".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


@dataclass
class DocumentIndex:
    doc_id: str
    meta: dict
    chunks: list[Chunk]
    vectors: np.ndarray
    _bm25: BM25Okapi | None = field(default=None, repr=False)

    @classmethod
    def build(cls, doc_id: str, meta: dict, chunks: list[Chunk]) -> "DocumentIndex":
        texts = [f"{c.section}\n{c.text}" for c in chunks]
        vectors = embeddings.embed_documents(texts)
        return cls(doc_id=doc_id, meta=meta, chunks=chunks, vectors=vectors)

    @property
    def bm25(self) -> BM25Okapi:
        if self._bm25 is None:
            self._bm25 = BM25Okapi([tokenize(f"{c.section} {c.text}") for c in self.chunks])
        return self._bm25

    def search(self, query: str, k: int = 6, candidates: int = 25, rrf_k: int = 60) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        dense_scores = self.vectors @ embeddings.embed_query(query)
        dense_rank = np.argsort(-dense_scores)[:candidates]

        q_tokens = tokenize(query)
        fused: dict[int, float] = {}
        for rank, idx in enumerate(dense_rank):
            fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (rrf_k + rank)
        if q_tokens:
            bm25_scores = self.bm25.get_scores(q_tokens)
            for rank, idx in enumerate(np.argsort(-bm25_scores)[:candidates]):
                if bm25_scores[idx] > 0:
                    fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (rrf_k + rank)

        ranked = sorted(fused.items(), key=lambda x: -x[1])[:k]
        # Present in document order so the LLM reads excerpts coherently.
        ranked.sort(key=lambda x: x[0])
        return [(self.chunks[i], score) for i, score in ranked]

    # ── persistence ──────────────────────────────────────────────────────
    def save(self, directory: str) -> None:
        os.makedirs(directory, exist_ok=True)
        base = os.path.join(directory, self.doc_id)
        np.save(base + ".npy", self.vectors.astype(np.float16))
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump({"meta": self.meta, "chunks": [c.to_dict() for c in self.chunks]}, f)

    @classmethod
    def load(cls, directory: str, doc_id: str) -> "DocumentIndex | None":
        base = os.path.join(directory, doc_id)
        try:
            with open(base + ".json", encoding="utf-8") as f:
                data = json.load(f)
            vectors = np.load(base + ".npy").astype(np.float32)
        except (OSError, ValueError):
            return None
        chunks = [Chunk(**c) for c in data["chunks"]]
        if len(chunks) != len(vectors):
            return None
        return cls(doc_id=doc_id, meta=data["meta"], chunks=chunks, vectors=vectors)
