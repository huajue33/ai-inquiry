import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from starlette.concurrency import run_in_threadpool

from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.conversation import Conversation, ChatMessage
from app.core.security import get_current_user

router = APIRouter()


class ConversationItem(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationList(BaseModel):
    conversations: list[ConversationItem]


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    thinking: Optional[str] = None
    suggestions: list = []
    duration: Optional[int] = None
    created_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    messages: list[MessageItem]


class UpdateTitleRequest(BaseModel):
    title: str


class SaveMessageRequest(BaseModel):
    conversation_id: str
    role: str
    content: str
    thinking: Optional[str] = None
    suggestions: list = []
    duration: Optional[int] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


async def _generate_title_background(conversation_id: str, user_message: str):
    """后台任务：用 LLM 生成标题并更新数据库。

    FastAPI 的 BackgroundTasks 原生支持 async 函数，会在响应返回后于事件循环中
    被正确 await，无需手动管理事件循环。
    """
    from app.services.title_service import generate_title

    title = await generate_title(user_message)

    def _persist():
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conv and conv.title == "新对话":
                conv.title = title
                db.commit()
        finally:
            db.close()

    # 同步 DB 写入放线程池，避免阻塞事件循环
    await run_in_threadpool(_persist)


@router.get("/", response_model=ConversationList)
async def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户的对话列表"""
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id, Conversation.is_deleted == 0)
        .order_by(desc(Conversation.updated_at))
        .limit(50)
        .all()
    )
    return ConversationList(
        conversations=[
            ConversationItem(
                id=c.id,
                title=c.title,
                created_at=str(c.created_at),
                updated_at=str(c.updated_at),
            )
            for c in convs
        ]
    )


@router.post("/create")
async def create_conversation(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建新对话"""
    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=user.id,
        title="新对话",
    )
    db.add(conv)
    db.commit()
    return {"id": conv.id, "title": conv.title}


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取对话详情（含消息）"""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        messages=[
            MessageItem(
                id=msg.id,
                role=msg.role,
                content=msg.content or "",
                thinking=msg.thinking,
                suggestions=msg.suggestions_json or [],
                duration=msg.duration,
                created_at=str(msg.created_at),
            )
            for msg in messages
        ],
    )


@router.put("/{conversation_id}/title")
async def update_title(
    conversation_id: str,
    request: UpdateTitleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新对话标题"""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    conv.title = request.title
    db.commit()
    return {"ok": True}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """逻辑删除对话"""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    conv.is_deleted = 1
    db.commit()
    return {"ok": True}


@router.post("/message")
async def save_message(
    request: SaveMessageRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存一条消息到对话"""
    # 确保对话存在，不存在则自动创建
    conv = db.query(Conversation).filter(
        Conversation.id == request.conversation_id,
        Conversation.user_id == user.id,
    ).first()

    is_new_conversation = False
    if not conv:
        conv = Conversation(
            id=request.conversation_id,
            user_id=user.id,
            title="新对话",
        )
        db.add(conv)
        db.flush()
        is_new_conversation = True

    # 保存消息
    msg = ChatMessage(
        conversation_id=request.conversation_id,
        role=request.role,
        content=request.content,
        thinking=request.thinking,
        suggestions_json=request.suggestions if request.suggestions else None,
        duration=request.duration,
        prompt_tokens=request.prompt_tokens,
        completion_tokens=request.completion_tokens,
        total_tokens=request.total_tokens,
    )
    db.add(msg)
    db.commit()

    # 如果是新对话的第一条用户消息，后台生成标题
    if is_new_conversation and request.role == "user" and request.content:
        background_tasks.add_task(
            _generate_title_background, request.conversation_id, request.content
        )

    return {"id": msg.id}
