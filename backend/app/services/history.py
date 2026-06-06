"""对话历史加载：按 token 预算的滑动窗口。

设计取舍（询价场景）：
- 对话多为"短、事务性"的一问一答，追问（"第二个""刚才那个""对比一下"）几乎只引用
  紧邻的上一轮。因此保留最近若干轮的**完整文本**远比"摘要很多轮"更有价值，尤其要
  完整保留 {#id=N} 标记、价格、品名，让 ID 复用可靠。
- 不再做 150 字截断、不再做 LLM 摘要（有损 + 多一次调用 + 失败点）。
- 从最近往前累加，直到 token 预算用尽即停（硬窗口）；按"轮"对齐，窗口从用户消息开始。
"""
from langchain_core.messages import HumanMessage, AIMessage

from app.database import SessionLocal
from app.models.conversation import ChatMessage as ChatMessageModel

# 上下文窗口的 token 预算
MAX_CONTEXT_TOKENS = 2500
# 单条消息字符上限（仅防止极端长消息撑爆窗口；远高于足以容纳 ID/价格的长度）
MAX_MSG_CHARS = 1200
# 最多从 DB 取多少条参与窗口计算（限制查询规模）
MAX_DB_MESSAGES = 30


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数：CJK 字符约 1 token，其余约 4 字符 1 token。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + other // 4 + 1


def _cap(content: str) -> str:
    """对极端超长的单条消息做兜底截断（保留开头）。"""
    if len(content) > MAX_MSG_CHARS:
        return content[:MAX_MSG_CHARS] + "..."
    return content


def load_history(conversation_id: str) -> list[AIMessage | HumanMessage]:
    """加载对话历史，按 token 预算的滑动窗口返回最近的若干轮（时间正序）。"""
    if not conversation_id:
        return []

    db = SessionLocal()
    try:
        rows = (
            db.query(ChatMessageModel)
            .filter(ChatMessageModel.conversation_id == conversation_id)
            .order_by(ChatMessageModel.created_at.desc())
            .limit(MAX_DB_MESSAGES)
            .all()
        )
        # 最新在前
        raw = [(r.role, r.content or "") for r in rows]
    finally:
        db.close()

    # 从最新往旧累加，直到超出 token 预算
    selected: list[tuple[str, str]] = []  # 仍是"最新在前"
    total = 0
    for role, content in raw:
        content = _cap(content)
        tokens = _estimate_tokens(content)
        if selected and total + tokens > MAX_CONTEXT_TOKENS:
            break
        selected.append((role, content))
        total += tokens

    # 转为时间正序
    selected.reverse()

    # 按"轮"对齐：窗口应从用户消息开始，丢掉开头悬空的助手消息
    while selected and selected[0][0] != "user":
        selected.pop(0)

    return _to_messages(selected)


def _to_messages(raw: list[tuple[str, str]]) -> list[AIMessage | HumanMessage]:
    """将(角色, 内容)元组列表转换为 LangChain 消息对象列表。"""
    msgs: list[AIMessage | HumanMessage] = []
    for role, content in raw:
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
    return msgs
