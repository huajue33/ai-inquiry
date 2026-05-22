import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services import ai_service
from app.models.user import User
from app.core.security import get_current_user

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, user: User = Depends(get_current_user)):
    """非流式接口"""
    conversation_id = request.conversation_id or str(uuid.uuid4())

    result = await ai_service.chat(request.message, conversation_id)

    return ChatResponse(
        reply=result["reply"],
        cards=result["cards"],
        suggestions=result["suggestions"],
        conversation_id=conversation_id,
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest, user: User = Depends(get_current_user)):
    """流式接口 - SSE（支持思考模式）"""
    conversation_id = request.conversation_id or str(uuid.uuid4())

    return StreamingResponse(
        ai_service.chat_stream(request.message, conversation_id, request.enable_thinking),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
