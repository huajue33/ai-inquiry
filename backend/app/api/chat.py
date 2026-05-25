import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services import ai_service
from app.models.user import User
from app.core.security import get_current_user
from app.core.permissions import current_user_var
from app.tools.price_tools import reset_permission_cache

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, user: User = Depends(get_current_user)):
    """非流式接口"""
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # 注入当前用户到 ContextVar，供 LangChain tools 同步函数读取
    token = current_user_var.set(user)
    reset_permission_cache()
    try:
        result = await ai_service.chat(request.message, conversation_id)
    finally:
        current_user_var.reset(token)

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

    # 把 user 也带给生成器（StreamingResponse 内的迭代发生在另一个上下文，
    # 需要在生成器内部重新 set 一次 ContextVar）
    async def event_generator():
        token = current_user_var.set(user)
        reset_permission_cache()
        try:
            async for chunk in ai_service.chat_stream(
                request.message, conversation_id, request.enable_thinking
            ):
                yield chunk
        finally:
            current_user_var.reset(token)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
