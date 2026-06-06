"""
助手消息的服务端持久化。

设计动机：原本助手回复完全依赖前端在 onDone 回调里调用 /conversations/message
保存，一旦用户中途关闭页面、断网或点击「停止」，回复就永久丢失，且 usage/duration
由客户端上报存在被篡改/漏报的风险。

这里在 SSE 流结束（正常完成或客户端断开）时由服务端兜底持久化，内容/思考/usage/
duration 均以服务端为准。用户消息仍由前端在发送时保存（独立的已完成请求，本身可靠，
并顺带触发标题生成），因此本模块只负责 assistant 角色，避免与前端重复保存。
"""
import logging
from typing import Optional

from app.database import SessionLocal
from app.models.conversation import Conversation, ChatMessage

logger = logging.getLogger(__name__)


def save_assistant_message(
    conversation_id: str,
    user_id: int,
    content: str,
    thinking: str = "",
    suggestions: Optional[list] = None,
    duration_ms: Optional[int] = None,
    usage: Optional[dict] = None,
) -> None:
    """落库一条助手消息（同步，供流结束/断开时的清理阶段直接调用）。

    - conversation_id / user_id 缺失，或 content 与 thinking 均为空时，直接跳过。
    - 对话不存在时防御性补建（正常情况下前端保存用户消息时已创建）。
    - 任何异常只记日志、回滚，绝不向上抛，避免影响清理流程。
    """
    if not conversation_id or not user_id:
        return
    if not (content or thinking):
        return

    usage = usage or {}
    db = SessionLocal()
    try:
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            conv = Conversation(
                id=conversation_id,
                user_id=user_id,
                title="新对话",
            )
            db.add(conv)
            db.flush()

        msg = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=content or "",
            thinking=thinking or None,
            suggestions_json=suggestions or None,
            duration=duration_ms,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
        db.add(msg)
        db.commit()
    except Exception as e:
        logger.warning(f"持久化助手消息失败 (conversation_id={conversation_id}): {e}")
        db.rollback()
    finally:
        db.close()
