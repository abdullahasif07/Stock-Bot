from fastapi.responses import JSONResponse

from ...models.schemas import ChatRequest
from ...services import chat_service
from ..streaming import primed_stream


class ChatHandler:

    @staticmethod
    async def send_message(payload: ChatRequest):
        kind, result = await chat_service.handle_message(
            payload.message,
            [m.model_dump() for m in payload.history],
            payload.context.model_dump(),
        )
        if kind == "clarification":
            return JSONResponse(content=result)
        return await primed_stream(result)
