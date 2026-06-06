from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    enable_thinking: bool = False
    enable_web_search: bool = False
    model: Optional[str] = None
