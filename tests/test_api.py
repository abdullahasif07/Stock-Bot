import io

from fastapi.testclient import TestClient

from backend import main, security
from backend.services import chat_service, stock_service
from backend.utils import quota

client = TestClient(main.app)
XFF = {"X-Forwarded-For": "203.0.113.7"}


def test_status_and_health():
    assert client.get("/api/health").json() == {"status": "ok"}
    body = client.get("/api/status").json()
    assert body["access_code_required"] is False
    assert "ai_requests" in body["budgets"]


def test_unknown_api_route_is_json_404():
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"detail": "Not found"}


def test_scanner_paths_are_404(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "favicon.ico").write_bytes(b"ico")
    monkeypatch.setattr(main, "BUILD_DIR", str(tmp_path))
    assert client.get("/").text == "<html>app</html>"
    assert client.head("/").status_code == 200
    assert client.get("/favicon.ico").status_code == 200
    for path in ("/wp-login.php", "/.env", "/.git/config", "/admin", "/../etc/passwd"):
        assert client.get(path).status_code == 404, path


def test_general_chat_streams(fake_gemini):
    r = client.post("/api/chat", json={"message": "What is a dividend?", "history": []}, headers=XFF)
    assert r.status_code == 200
    assert r.text == "Revenue grew strongly [1]."
    assert len(fake_gemini["json"]) == 1 and len(fake_gemini["stream"]) == 1  # 2 LLM calls total


def test_stock_quote_flow_uses_quote_data(fake_gemini, monkeypatch):
    fake_gemini["intent"] = {"intent": "get_specific_data", "entity": "Apple", "ticker": "AAPL"}
    monkeypatch.setattr(chat_service.sec_service, "lookup_ticker", lambda t: {"ticker": t})
    monkeypatch.setattr(stock_service, "get_stock_quote", lambda t: {"symbol": t, "price": "123.45"})
    r = client.post("/api/chat", json={"message": "Apple price?"}, headers=XFF)
    assert r.status_code == 200
    assert "123.45" in fake_gemini["stream"][0]


def test_clarification_returns_json(fake_gemini, monkeypatch):
    fake_gemini["intent"] = {"intent": "get_specific_data", "entity": "apple", "ticker": None}
    monkeypatch.setattr(chat_service.sec_service, "resolve_company", lambda q: (None, [
        {"ticker": "AAPL", "name": "Apple Inc."}, {"ticker": "APLE", "name": "Apple Hospitality"}]))
    r = client.post("/api/chat", json={"message": "apple stock"}, headers=XFF)
    assert r.headers["content-type"].startswith("application/json")
    assert [c["symbol"] for c in r.json()["choices"]] == ["AAPL", "APLE"]


def test_per_ip_rate_limit(fake_gemini):
    for _ in range(3):
        assert client.post("/api/chat", json={"message": "hi"}, headers=XFF).status_code == 200
    r = client.post("/api/chat", json={"message": "hi"}, headers=XFF)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    # A different visitor is unaffected
    assert client.post("/api/chat", json={"message": "hi"}, headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 200


def test_spoofed_forwarded_for_does_not_bypass_limit(fake_gemini):
    # Client prepends fake IPs; the proxy-appended (right-most) one is used.
    for i in range(3):
        client.post("/api/chat", json={"message": "hi"}, headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"})
    r = client.post("/api/chat", json={"message": "hi"}, headers={"X-Forwarded-For": "10.9.9.9, 203.0.113.9"})
    assert r.status_code == 429


def test_global_quota_exhaustion_returns_429(monkeypatch):
    monkeypatch.setattr(quota.gemini_budget, "limit", 0)
    r = client.post("/api/chat", json={"message": "hi"}, headers={"X-Forwarded-For": "192.0.2.50"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "quota_exceeded"


def test_input_validation():
    assert client.post("/api/chat", json={"message": ""}, headers=XFF).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 5000}, headers=XFF).status_code == 422
    r = client.post("/api/chat", content=b"{" + b" " * 300_000 + b"}",
                    headers={**XFF, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_access_code(monkeypatch, fake_gemini):
    monkeypatch.setattr(security, "DEMO_ACCESS_CODE", "s3cret")
    assert client.post("/api/chat", json={"message": "hi"}, headers=XFF).status_code == 401
    assert client.get("/api/market/news").status_code == 401
    ok = client.post("/api/chat", json={"message": "hi"}, headers={**XFF, "X-Access-Code": "s3cret"})
    assert ok.status_code == 200


def test_upload_then_query_with_citations(fake_gemini):
    doc = ("Item 1. Business\nWe build rockets and satellites.\n"
           "Item 7. MD&A\nRevenue grew 30% to $9.2 billion driven by launch services.\n") * 10
    r = client.post("/api/rag/upload", files={"file": ("notes.txt", io.BytesIO(doc.encode()), "text/plain")}, headers=XFF)
    assert r.status_code == 200, r.text
    meta = r.json()["document"]
    assert meta["doc_id"].startswith("upload_") and meta["chunks"] > 0

    q = client.post("/api/rag/query", json={"doc_id": meta["doc_id"], "question": "How fast did revenue grow?"}, headers=XFF)
    assert q.status_code == 200
    assert q.text.startswith("Revenue grew strongly [1].")
    assert "**Sources**" in q.text and "[1]" in q.text
    assert "EXCERPTS" in fake_gemini["stream"][0]


def test_upload_rejects_bad_type_and_unknown_doc(fake_gemini):
    r = client.post("/api/rag/upload", files={"file": ("x.exe", io.BytesIO(b"MZ" * 200), "application/octet-stream")}, headers=XFF)
    assert r.status_code == 422
    q = client.post("/api/rag/query", json={"doc_id": "upload_doesnotexist", "question": "hi"}, headers=XFF)
    assert "no longer loaded" in q.text
    q = client.post("/api/rag/query", json={"doc_id": "../../etc/passwd", "question": "hi"}, headers=XFF)
    assert "no longer loaded" in q.text
