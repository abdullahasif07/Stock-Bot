from fastapi import APIRouter, Depends, File, UploadFile

from ..config import CHAT_PER_MINUTE, CHAT_PER_DAY, RAG_INGEST_PER_DAY, UPLOAD_PER_DAY
from ..models.schemas import RagInitiateRequest, RagQueryRequest
from ..security import rate_limit
from .handlers.rag_handler import RagHandler

router = APIRouter(prefix="/api/rag", tags=["RAG"])


@router.post("/initiate", dependencies=[Depends(rate_limit("document", per_minute=3, per_day=RAG_INGEST_PER_DAY))])
async def rag_initiate(payload: RagInitiateRequest):
    return await RagHandler.initiate(payload)


@router.post("/upload", dependencies=[Depends(rate_limit("upload", per_minute=2, per_day=UPLOAD_PER_DAY))])
async def rag_upload(file: UploadFile = File(...)):
    return await RagHandler.upload(file)


@router.post("/query", dependencies=[Depends(rate_limit("chat", CHAT_PER_MINUTE, CHAT_PER_DAY))])
async def rag_query(payload: RagQueryRequest):
    return await RagHandler.query(payload)
