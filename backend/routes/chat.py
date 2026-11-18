from fastapi import APIRouter, Depends

from ..config import CHAT_PER_MINUTE, CHAT_PER_DAY
from ..models.schemas import ChatRequest
from ..security import rate_limit
from .handlers.chat_handler import ChatHandler

router = APIRouter(prefix="/api", tags=["Chat"])


@router.post("/chat", dependencies=[Depends(rate_limit("chat", CHAT_PER_MINUTE, CHAT_PER_DAY))])
async def chat(payload: ChatRequest):
    """Streams the assistant reply as text, or returns JSON when the bot needs
    the user to pick between several matching tickers."""
    return await ChatHandler.send_message(payload)
