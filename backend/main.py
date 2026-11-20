import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from google.genai import errors as genai_errors

from .config import (
    ALPHA_VANTAGE_API_KEY, BUILD_DIR, CORS_ORIGINS, DEMO_ACCESS_CODE, GEMINI_API_KEY,
    GEMINI_MODEL, MAX_UPLOAD_MB, CHAT_PER_DAY,
)
from .routes import chat, market, rag
from .security import require_access_code
from .utils.gemini import GeminiUnavailable
from .utils.quota import QuotaExceeded, alpha_vantage_budget, filing_budget, gemini_budget

MAX_JSON_BODY = 256 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("SKIP_WARMUP") != "1":
        from .rag.embeddings import warmup
        # Load the embedding model in the background so the first analysis is fast.
        asyncio.get_running_loop().run_in_executor(None, warmup)
    yield


app = FastAPI(
    title="StockBot API",
    description="AI financial assistant: live market data (Alpha Vantage), Gemini chat, "
                "and RAG over SEC annual reports.",
    version="2.0.0",
    lifespan=lifespan,
)

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Access-Code"],
    )


@app.middleware("http")
async def guard_and_headers(request: Request, call_next):
    # Reject oversized bodies before they're read.
    length = request.headers.get("content-length")
    if request.method == "POST" and length and length.isdigit():
        limit = (MAX_UPLOAD_MB * 1024 * 1024 + 64 * 1024) if request.url.path == "/api/rag/upload" else MAX_JSON_BODY
        if int(length) > limit:
            return JSONResponse(status_code=413, content={"detail": {"code": "too_large", "message": "Request body too large."}})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


# ── Error mapping ───────────────────────────────────────────────────────────
@app.exception_handler(QuotaExceeded)
async def quota_handler(_req, exc: QuotaExceeded):
    return JSONResponse(status_code=429, content={"detail": {"code": "quota_exceeded", "message": str(exc)}})


@app.exception_handler(GeminiUnavailable)
async def gemini_missing_handler(_req, exc: GeminiUnavailable):
    return JSONResponse(status_code=503, content={"detail": {"code": "ai_unavailable", "message": str(exc)}})


@app.exception_handler(genai_errors.APIError)
async def gemini_error_handler(_req, exc: genai_errors.APIError):
    print(f"[GEMINI] API error {getattr(exc, 'code', '?')}: {exc}")
    return JSONResponse(status_code=503, content={"detail": {
        "code": "ai_unavailable",
        "message": "The AI model is busy or unavailable right now. Please try again shortly."}})


# ── Routes ──────────────────────────────────────────────────────────────────
app.include_router(chat.router)
app.include_router(market.router)
app.include_router(rag.router)


@app.get("/api/health", tags=["System"])
def health():
    return {"status": "ok"}


@app.get("/api/status", tags=["System"])
def status():
    """Public demo status: which integrations are configured and how much of
    today's shared budget is left."""
    return {
        "access_code_required": bool(DEMO_ACCESS_CODE),
        "model": GEMINI_MODEL,
        "integrations": {"gemini": bool(GEMINI_API_KEY), "alpha_vantage": bool(ALPHA_VANTAGE_API_KEY)},
        "budgets": {
            "ai_requests": gemini_budget.snapshot(),
            "market_data_requests": alpha_vantage_budget.snapshot(),
            "new_documents": filing_budget.snapshot(),
        },
        "per_visitor_daily_messages": CHAT_PER_DAY,
    }


@app.get("/api/access-check", tags=["System"], dependencies=[Depends(require_access_code)])
def access_check():
    return {"ok": True}


@app.api_route("/api/{path:path}", methods=["GET", "POST"], include_in_schema=False)
def api_not_found(path: str):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


# ── Static SPA (production build) ───────────────────────────────────────────
assets_dir = os.path.join(BUILD_DIR, "assets")
if os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_spa(full_path: str):
    """The SPA has no client-side routes, so only "/" serves index.html. Anything
    else that isn't a real build file (bot scans for /wp-login.php, /.env, ...)
    gets a plain 404 instead of the app page."""
    if full_path:
        candidate = os.path.normpath(os.path.join(BUILD_DIR, full_path))
        if candidate.startswith(BUILD_DIR + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)  # favicon, manifest, etc.
        return PlainTextResponse("Not found", status_code=404)
    index_path = os.path.join(BUILD_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={
        "message": "Frontend build not found. In development run the Vite dev server (make dev)."})
