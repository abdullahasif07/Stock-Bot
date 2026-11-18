"""Central configuration. Everything is driven by environment variables so the
same image runs locally, on Render, AWS App Runner, Fly.io, etc."""
import os

from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BACKEND_DIR, ".env"))
load_dotenv()  # also allow a project-root .env


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


# ── API keys ────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY")

# ── Models ──────────────────────────────────────────────────────────────────
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
# Tried in order when the primary model is overloaded (503/429) or retired (404).
GEMINI_FALLBACK_MODELS = _list("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-3.1-flash-lite")
# Small, fast model for the quick intent-classification call before each answer.
GEMINI_FAST_MODEL = os.environ.get("GEMINI_FAST_MODEL", "gemini-3.1-flash-lite")
# Gemini 3 models "think" before answering by default, which adds seconds of
# latency. minimal|low|medium|high; empty = model default.
GEMINI_THINKING_LEVEL = os.environ.get("GEMINI_THINKING_LEVEL", "minimal").strip().upper()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# ── External services ───────────────────────────────────────────────────────
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
# SEC asks automated clients to identify themselves with a contact address.
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "StockBot-Demo/2.0 stockbot-demo@example.com")

# ── Demo protection (keeps a public demo from burning through API quotas) ───
# Optional shared code; when set, every /api call needs header X-Access-Code.
DEMO_ACCESS_CODE = os.environ.get("DEMO_ACCESS_CODE", "").strip()

# Global daily budgets (reset at 00:00 UTC).
GEMINI_DAILY_LIMIT = _int("GEMINI_DAILY_LIMIT", 300)
AV_DAILY_LIMIT = _int("AV_DAILY_LIMIT", 25)            # Alpha Vantage free tier = 25/day
FILING_INGEST_DAILY_LIMIT = _int("FILING_INGEST_DAILY_LIMIT", 20)

# Per-IP limits.
CHAT_PER_MINUTE = _int("CHAT_PER_MINUTE", 6)
CHAT_PER_DAY = _int("CHAT_PER_DAY", 40)
RAG_INGEST_PER_DAY = _int("RAG_INGEST_PER_DAY", 5)
UPLOAD_PER_DAY = _int("UPLOAD_PER_DAY", 5)

# Input limits.
MAX_MESSAGE_CHARS = _int("MAX_MESSAGE_CHARS", 1000)
MAX_HISTORY_MESSAGES = _int("MAX_HISTORY_MESSAGES", 8)
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 5)

# Number of proxies in front of the app that append to X-Forwarded-For
# (1 for Render / App Runner / Fly). Set 0 when exposed directly.
TRUSTED_PROXY_HOPS = _int("TRUSTED_PROXY_HOPS", 1)

# ── CORS (only needed when the frontend is hosted on a different origin) ────
CORS_ORIGINS = _list("CORS_ORIGINS", "http://localhost:5173")

# ── Caching (seconds) ───────────────────────────────────────────────────────
MARKET_CACHE_TTL = _int("MARKET_CACHE_TTL", 12 * 3600)
NEWS_CACHE_TTL = _int("NEWS_CACHE_TTL", 6 * 3600)
IPO_CACHE_TTL = _int("IPO_CACHE_TTL", 24 * 3600)
QUOTE_CACHE_TTL = _int("QUOTE_CACHE_TTL", 30 * 60)
FUNDAMENTALS_CACHE_TTL = _int("FUNDAMENTALS_CACHE_TTL", 24 * 3600)

# ── Paths ───────────────────────────────────────────────────────────────────
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BACKEND_DIR, "data"))
CACHE_DIR = os.path.join(DATA_DIR, "cache")
FILINGS_DIR = os.path.join(DATA_DIR, "filings")
INDEX_DIR = os.path.join(DATA_DIR, "indexes")
MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", os.path.join(DATA_DIR, "models"))
BUILD_DIR = os.path.abspath(os.path.join(BACKEND_DIR, "..", "react-frontend", "dist"))

for _d in (CACHE_DIR, FILINGS_DIR, INDEX_DIR):
    os.makedirs(_d, exist_ok=True)
