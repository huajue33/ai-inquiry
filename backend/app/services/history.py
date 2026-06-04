from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.database import SessionLocal
from app.models.conversation import ChatMessage as ChatMessageModel

# 摘要用 LLM（惰性初始化，无 streaming）
_summary_llm: ChatOpenAI | None = None


def _get_summary_llm() -> ChatOpenAI:
    """惰性初始化并返回用于对话摘要的LLM实例"""
    global _summary_llm
    if _summary_llm is None:
        settings = get_settings()
        _summary_llm = ChatOpenAI(
            base_url=settings.dashscope_base_url,
            api_key=settings.dashscope_api_key,
            model=settings.dashscope_model,
        )
    return _summary_llm


def load_history(conversation_id: str) -> list[AIMessage | HumanMessage]:
    """从 DB 加载近期对话，超预算时自动摘要压缩。

    策略：
    1. 逐条截断 AI 长回复至 150 字
    2. 总长在预算内 → 直接返回
    3. 超出 → 保留最近 2 轮，更早的由 LLM 压缩为摘要
    """
    if not conversation_id:
        return []

    db = SessionLocal()
    try:
        rows = (
            db.query(ChatMessageModel)
            .filter(ChatMessageModel.conversation_id == conversation_id)
            .order_by(ChatMessageModel.created_at.desc())
            .limit(10)
            .all()
        )
        if not rows:
            return []
        raw = [(r.role, r.content) for r in reversed(rows)]
    finally:
        db.close()

    return _build(raw)


def _build(raw: list[tuple[str, str]], max_tokens: int = 1500) -> list[AIMessage | HumanMessage]:
    """截断 + 摘要压缩。"""
    truncated = _truncate_ai(raw)

    char_budget = int(max_tokens / 1.5)
    if sum(len(c) for _, c in truncated) <= char_budget:
        return _to_messages(truncated)

    keep = 4  # 保留最近 2 轮
    old = truncated[:-keep] if len(truncated) > keep else []
    recent = truncated[-keep:] if len(truncated) > keep else truncated

    if not old:
        return _to_messages(recent)

    summary = _summarize(_to_text(old))
    return [AIMessage(content=f"[历史摘要] {summary}")] + _to_messages(recent)


def _truncate_ai(raw: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """截断AI回复超过150字的内容，减少上下文占用"""
    result = []
    for role, content in raw:
        if role == "assistant" and len(content) > 150:
            result.append((role, content[:150] + "..."))
        else:
            result.append((role, content))
    return result


def _to_messages(raw: list[tuple[str, str]]) -> list[AIMessage | HumanMessage]:
    """将(角色, 内容)元组列表转换为LangChain消息对象列表"""
    msgs: list[AIMessage | HumanMessage] = []
    for role, content in raw:
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
    return msgs


def _to_text(raw: list[tuple[str, str]]) -> str:
    """将(角色, 内容)元组列表转换为带角色前缀的纯文本字符串"""
    return "\n".join(
        f"{'用户' if role == 'user' else '助手'}: {content}"
        for role, content in raw
    )


def _summarize(text: str) -> str:
    """使用LLM将较早的对话压缩为简洁摘要，保留关键查询和价格信息"""
    llm = _get_summary_llm()
    resp = llm.invoke([
        SystemMessage(
            content="你是一个对话摘要助手。将以下对话压缩为简洁的摘要（100字以内），"
            "保留关键信息：查询的产品、价格数据、用户意图。"
        ),
        HumanMessage(content=text),
    ])
    return resp.content
