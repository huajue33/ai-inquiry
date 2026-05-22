from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    enable_thinking: bool = False


class CardData(BaseModel):
    type: str
    data: dict


class ChatResponse(BaseModel):
    reply: str
    cards: list[CardData] = []
    suggestions: list[str] = []
    conversation_id: str
