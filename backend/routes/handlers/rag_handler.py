import asyncio

from fastapi import HTTPException, UploadFile

from ...config import MAX_UPLOAD_MB
from ...models.schemas import RagInitiateRequest, RagQueryRequest
from ...services import rag_service, sec_service
from ..streaming import primed_stream


class RagHandler:

    @staticmethod
    async def initiate(payload: RagInitiateRequest) -> dict:
        """Resolve a company name/ticker and prepare its latest annual report.
        Returns either a clarification (several matches) or the document metadata."""
        confident, candidates = await asyncio.to_thread(sec_service.resolve_company, payload.company)
        if not confident:
            if not candidates:
                raise HTTPException(404, detail={"code": "not_found", "message":
                    f"No SEC-registered company matches \"{payload.company}\". Try the ticker symbol."})
            return {
                "response_type": "clarification",
                "message": f"I found several companies matching \"{payload.company}\". Which one?",
                "choices": [{"symbol": c["ticker"], "name": c["name"]} for c in candidates],
            }
        try:
            doc = await asyncio.to_thread(rag_service.build_filing_index, confident["ticker"])
        except rag_service.DocumentError as e:
            raise HTTPException(422, detail={"code": "document_error", "message": str(e)})
        return {"response_type": "document", "document": doc}

    @staticmethod
    async def upload(file: UploadFile) -> dict:
        limit = MAX_UPLOAD_MB * 1024 * 1024
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, detail={"code": "too_large", "message": f"Max upload size is {MAX_UPLOAD_MB} MB."})
        try:
            doc = await asyncio.to_thread(rag_service.build_upload_index, file.filename or "document.txt", data)
        except rag_service.DocumentError as e:
            raise HTTPException(422, detail={"code": "document_error", "message": str(e)})
        except Exception as e:
            print(f"[RAG] Upload parse failed: {type(e).__name__}: {e}")
            raise HTTPException(422, detail={"code": "document_error", "message": "Couldn't read that file."})
        return {"response_type": "document", "document": doc}

    @staticmethod
    async def query(payload: RagQueryRequest):
        return await primed_stream(rag_service.answer(
            payload.doc_id, payload.question, [m.model_dump() for m in payload.history]
        ))
