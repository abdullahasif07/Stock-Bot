"""RAG orchestration: build/load document indexes and answer questions.

Efficiency vs. the previous LangChain/FAISS pipeline:
* Embedding model is loaded once per process (was re-created per document).
* Indexes are persisted to disk per filing accession, so a 10-K is embedded
  once ever, not once per server start / per user.
* Hybrid BM25 + dense retrieval with section-aware chunks and citations.
* One Gemini call per question (the separate "is this relevant?" LLM call was
  removed; the answer prompt handles small talk itself) — halves LLM usage.
"""
import asyncio
import io
import re
import secrets
import threading
import time
from collections import OrderedDict
from typing import AsyncIterator

from ..config import INDEX_DIR
from ..prompts import rag as prompts
from ..rag.chunking import chunk_document
from ..rag.index import DocumentIndex
from ..utils import gemini
from ..utils.quota import filing_budget, QuotaExceeded
from . import sec_service

MAX_LOADED = 8
UPLOAD_TTL = 3 * 3600
MAX_DOC_CHARS = 2_000_000

_loaded: "OrderedDict[str, tuple[float, DocumentIndex]]" = OrderedDict()
_loaded_lock = threading.Lock()
_build_locks: dict[str, threading.Lock] = {}


class DocumentError(Exception):
    pass


def _remember(index: DocumentIndex) -> None:
    with _loaded_lock:
        _loaded[index.doc_id] = (time.time(), index)
        _loaded.move_to_end(index.doc_id)
        while len(_loaded) > MAX_LOADED:
            _loaded.popitem(last=False)


def get_index(doc_id: str) -> DocumentIndex | None:
    with _loaded_lock:
        entry = _loaded.get(doc_id)
        if entry:
            if doc_id.startswith("upload_") and time.time() - entry[0] > UPLOAD_TTL:
                del _loaded[doc_id]
                return None
            _loaded.move_to_end(doc_id)
            return entry[1]
    if doc_id.startswith("upload_") or not re.fullmatch(r"[A-Z0-9\-]+_[\w\-]+", doc_id):
        return None
    index = DocumentIndex.load(INDEX_DIR, doc_id)
    if index:
        _remember(index)
    return index


def _public_meta(index: DocumentIndex) -> dict:
    m = index.meta
    return {
        "doc_id": index.doc_id,
        "title": m.get("title"),
        "company_name": m.get("company_name"),
        "ticker": m.get("ticker"),
        "form": m.get("form"),
        "report_date": m.get("report_date"),
        "filing_date": m.get("filing_date"),
        "source_url": m.get("source_url"),
        "chunks": len(index.chunks),
    }


def build_filing_index(ticker: str) -> dict:
    """Blocking. Returns public metadata for the ticker's latest annual report."""
    company = sec_service.lookup_ticker(ticker)
    if not company:
        raise DocumentError(f"'{ticker}' is not a ticker registered with the SEC.")
    filing = None
    try:
        filing = sec_service.latest_annual_filing(company["cik"])
    except Exception as e:
        print(f"[RAG] Filing lookup failed for {ticker}: {e}")
    doc_id = f"{company['ticker']}_{filing['accession'] if filing else 'bundled'}"

    existing = get_index(doc_id)
    if existing:
        return _public_meta(existing)

    lock = _build_locks.setdefault(doc_id, threading.Lock())
    with lock:
        existing = get_index(doc_id)
        if existing:
            return _public_meta(existing)
        if not filing_budget.try_consume():
            raise QuotaExceeded("document processing")
        report = sec_service.get_annual_report(company["ticker"])
        if not report:
            raise DocumentError(f"Couldn't retrieve an annual report (10-K/20-F) for {company['name']}.")
        meta = {**report["meta"], "title": f"{company['name']} {report['meta'].get('form', '10-K')}"}
        doc_id = f"{company['ticker']}_{meta.get('accession', 'bundled')}"
        t0 = time.time()
        chunks = chunk_document(report["text"][:MAX_DOC_CHARS])
        index = DocumentIndex.build(doc_id, meta, chunks)
        index.save(INDEX_DIR)
        _remember(index)
        print(f"[RAG] Indexed {doc_id}: {len(chunks)} chunks in {time.time() - t0:.1f}s")
        return _public_meta(index)


def extract_upload_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > 300:
            raise DocumentError("PDF has too many pages (max 300).")
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if name.endswith((".htm", ".html")):
        return sec_service.html_to_text(data)
    if name.endswith((".txt", ".md", ".csv")):
        return data.decode("utf-8", errors="replace")
    raise DocumentError("Unsupported file type. Upload a PDF, HTML, TXT, MD or CSV file.")


def build_upload_index(filename: str, data: bytes) -> dict:
    text = extract_upload_text(filename, data).strip()
    if len(text) < 200:
        raise DocumentError("Couldn't extract enough text from that file (is it a scanned PDF?).")
    chunks = chunk_document(text[:MAX_DOC_CHARS])
    doc_id = "upload_" + secrets.token_urlsafe(16)  # unguessable → private to the uploader
    clean_name = re.sub(r"[^\w.\- ]", "", filename)[:80] or "document"
    index = DocumentIndex.build(doc_id, {"title": clean_name, "company_name": clean_name}, chunks)
    _remember(index)
    return _public_meta(index)


def _retrieval_query(question: str, history: list[dict]) -> str:
    """Short follow-ups ("and in 2023?") inherit the previous question's topic
    — a free alternative to an LLM query-rewrite call."""
    if len(question.split()) <= 6:
        prev = next((m["text"] for m in reversed(history) if m.get("role") == "user"), None)
        if prev:
            return f"{prev} {question}"
    return question


async def answer(doc_id: str, question: str, history: list[dict]) -> AsyncIterator[str]:
    index = await asyncio.to_thread(get_index, doc_id)
    if not index:
        yield "This document is no longer loaded (uploads expire after a few hours). Please start a new analysis."
        return

    hits = await asyncio.to_thread(index.search, _retrieval_query(question, history), 6)
    excerpts = "\n\n".join(
        f"[{n}] (Section: {chunk.section})\n{chunk.text}" for n, (chunk, _) in enumerate(hits, 1)
    )
    prompt = prompts.answer_prompt(
        doc_title=index.meta.get("title") or "the document",
        excerpts=excerpts,
        history=gemini.format_history(history[-4:], max_chars=600),
        question=question,
    )

    full = ""
    async for chunk in gemini.stream(prompt, system=prompts.SYSTEM, temperature=0.2):
        full += chunk
        yield chunk

    cited = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", full) if 0 < int(n) <= len(hits)})
    if cited:
        lines = [f"- **[{n}]** {hits[n - 1][0].section}" for n in cited]
        yield "\n\n---\n**Sources**\n" + "\n".join(lines)

