from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, Enum, ForeignKey, JSON, func
from app.database import Base


class Conversation(Base):
    """一次对话会话（归属某用户，逻辑删除）。"""
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(128), nullable=False, default="新对话")
    is_deleted = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    """对话中的单条消息（user / assistant）。"""
    __tablename__ = "chat_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False)
    role = Column(Enum("user", "assistant"), nullable=False)
    content = Column(Text, nullable=False, default="")
    thinking = Column(Text)
    suggestions_json = Column(JSON)
    duration = Column(Integer)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
