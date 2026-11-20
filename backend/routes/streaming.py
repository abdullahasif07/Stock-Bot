from typing import AsyncIterator

from fastapi.responses import StreamingResponse

from ..constants import MSG_INTERNAL_ERROR


async def primed_stream(agen: AsyncIterator[str], headers: dict | None = None) -> StreamingResponse:
    """Pull the first chunk *before* sending headers, so failures that happen
    up-front (quota exceeded, missing key, upstream down) become proper HTTP
    errors instead of a 200 with an error string in the body."""
    try:
        first = await agen.__anext__()
    except StopAsyncIteration:
        first = ""

    async def body():
        yield first
        try:
            async for chunk in agen:
                yield chunk
        except Exception as e:
            print(f"[STREAM] Error mid-stream: {type(e).__name__}: {e}")
            yield f"\n\n_{MSG_INTERNAL_ERROR}_"

    return StreamingResponse(body(), media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", **(headers or {})})
