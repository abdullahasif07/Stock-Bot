"""Run at image build time: download the embedding model and pre-index a few
popular annual reports so the deployed demo answers instantly.

    python -m backend.scripts.prebuild            # uses PREBUILD_TICKERS
    PREBUILD_TICKERS=AAPL,TSLA python -m backend.scripts.prebuild
"""
import glob
import os
import time

from backend.config import CACHE_DIR
from backend.rag.embeddings import warmup
from backend.services import rag_service


def main():
    warmup()
    tickers = [t.strip().upper() for t in os.environ.get("PREBUILD_TICKERS", "AAPL,AMZN,MSFT,NVDA").split(",") if t.strip()]
    for ticker in tickers:
        t0 = time.time()
        try:
            doc = rag_service.build_filing_index(ticker)
            print(f"[PREBUILD] {ticker}: {doc['doc_id']} ({doc['chunks']} chunks, {time.time() - t0:.0f}s)")
        except Exception as e:  # never fail the build because SEC was slow
            print(f"[PREBUILD] {ticker} skipped: {type(e).__name__}: {e}")
    # Don't ship today's usage counters inside the image.
    for path in glob.glob(os.path.join(CACHE_DIR, "quota_*.json")):
        os.remove(path)


if __name__ == "__main__":
    main()
