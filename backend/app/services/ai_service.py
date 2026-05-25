import json
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from app.config import get_settings
from app.core.prompts import SYSTEM_PROMPT
from app.core.permissions import (
    current_user_var,
    get_allowed_category_ids,
)
from app.database import SessionLocal
from app.models.conversation import ChatMessage as ChatMessageModel
from app.models.product import Category
from app.models.permission import UserCategoryPermission
from app.tools.price_tools import (
    query_latest_price,
    query_price_trend,
    query_price_ranking,
    compare_products,
    clarify_product,
)

settings = get_settings()

# LangChain LLM（用于 Agent 工具调用，非思考模式）
llm = ChatOpenAI(
    base_url=settings.dashscope_base_url,
    api_key=settings.dashscope_api_key,
    model=settings.dashscope_model,
    streaming=True,
    model_kwargs={"stream_options": {"include_usage": True}},
)

# 原生 OpenAI 客户端（用于思考模式的直接调用）
openai_client = AsyncOpenAI(
    api_key=settings.dashscope_api_key,
    base_url=settings.dashscope_base_url,
)

tools = [
    query_latest_price,
    query_price_trend,
    query_price_ranking,
    compare_products,
    clarify_product,
]

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("system", "{user_scope}"),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    max_iterations=8,
    handle_parsing_errors=True,
    return_intermediate_steps=True,
)


def _build_user_scope_prompt() -> str:
    """根据 ContextVar 中的当前用户，构造 "你能查的分类" 系统提示。

    返回示例：
      - admin/manager: "当前用户角色 admin，可访问全部分类。"
      - buyer 有授权: "当前用户为采购员，仅可访问以下二级分类：叶菜类、根茎类。
                    其他分类（如 调味品-食用油）请直接回复"无权访问"，不要尝试搜索。"
      - buyer 无授权: "当前用户没有任何分类的查看权限，请直接告知用户联系管理员。"
    """
    user = current_user_var.get()
    if user is None:
        return "当前匿名访问，无任何数据查询权限。"

    if user.role in ("admin", "manager"):
        return f"当前用户角色 {user.role}，可访问全部分类，无数据范围限制。"

    db = SessionLocal()
    try:
        # 直接读授权的二级分类名（不展开到三级，给 LLM 看更直观）
        rows = (
            db.query(Category.name, Category.parent_id)
            .join(
                UserCategoryPermission,
                UserCategoryPermission.category_id == Category.id,
            )
            .filter(UserCategoryPermission.user_id == user.id)
            .all()
        )
        if not rows:
            return (
                "【重要】当前用户为采购员，但**未被授权任何分类**。"
                "请直接告知用户：'你当前没有数据查询权限，请联系管理员授权'。"
                "不要调用任何查询工具。"
            )

        allowed = "、".join(r[0] for r in rows)

        # 列出所有二级分类，标出 "未授权" 的
        all_seconds = (
            db.query(Category.name)
            .filter(Category.level == 2)
            .all()
        )
        denied_names = sorted(set(c[0] for c in all_seconds) - set(r[0] for r in rows))
        denied_str = "、".join(denied_names[:20]) if denied_names else "无"

        return (
            f"【数据权限】当前用户为采购员（{user.real_name}），"
            f"**仅可访问以下二级分类**：{allowed}。\n"
            f"**禁止访问**：{denied_str}。\n"
            "如果用户询问的产品明显属于禁止访问的分类（例如询问"
            "调味品/食用油/醋/酱油 等而你没有该权限），"
            "**直接回复 '抱歉，你没有该分类的查询权限，请联系管理员'，不要调用任何工具**。"
            "如果不确定属于哪个分类，可以调用一次工具试探，但收到 '无权访问' 后不要重试。"
        )
    finally:
        db.close()


def _load_chat_history(conversation_id: str, max_turns: int = 5, max_tokens: int = 1500) -> list:
    """
    从数据库加载对话历史，转为 LangChain 消息格式。

    采销询价场景的上下文策略：
    1. 最多 5 轮（询价对话通常 3-5 轮就结束一个话题）
    2. 用户消息完整保留（通常很短，是查询意图）
    3. AI 回复只保留前 150 字摘要（完整回复太长，核心是让 AI 知道"上次回答了什么"）
    4. Token 预算 1500（给系统提示词 + 工具 schema + 新回复留足空间）
    5. 从最新往前取，保证追问上下文连贯
    """
    if not conversation_id:
        return []

    db = SessionLocal()
    try:
        messages = (
            db.query(ChatMessageModel)
            .filter(ChatMessageModel.conversation_id == conversation_id)
            .order_by(ChatMessageModel.created_at)
            .all()
        )

        if not messages:
            return []

        # 取最近 max_turns * 2 条
        recent = messages[-(max_turns * 2):]

        # 从后往前累计，超出预算则截断
        history = []
        total_chars = 0
        char_limit = int(max_tokens / 1.5)

        for msg in reversed(recent):
            content = msg.content or ""

            if msg.role == "assistant":
                # AI 回复只保留摘要（前150字），因为完整回复可能有大段表格
                if len(content) > 150:
                    content = content[:150] + "..."
            # 用户消息完整保留（通常很短）

            if total_chars + len(content) > char_limit:
                break

            total_chars += len(content)

            if msg.role == "user":
                history.insert(0, HumanMessage(content=content))
            elif msg.role == "assistant":
                history.insert(0, AIMessage(content=content))

        return history
    finally:
        db.close()


def _last_tool_observation(intermediate_steps) -> str:
    """从 agent 的 intermediate_steps 中拿最后一次工具的返回，用作降级答复"""
    if not intermediate_steps:
        return ""
    try:
        _action, observation = intermediate_steps[-1]
        return str(observation)[:600]
    except Exception:
        return ""


async def chat(message: str, conversation_id: str) -> dict:
    """Non-streaming: invoke the agent and return full response."""
    try:
        chat_history = _load_chat_history(conversation_id)
        result = await agent_executor.ainvoke({
            "input": message,
            "chat_history": chat_history,
            "user_scope": _build_user_scope_prompt(),
        })

        reply = result.get("output") or ""
        if not reply.strip():
            # max_iterations 触发或 LLM 没返回内容，用最后一次工具返回兜底
            fallback = _last_tool_observation(result.get("intermediate_steps", []))
            reply = fallback or "抱歉，没能从数据库找到匹配的结果。请尝试更具体的产品名或换个问法。"

        suggestions = [
            "查询今日蔬菜价格",
            "对比不同品牌食用油价格",
            "查看近7天鸡蛋价格趋势",
        ]

        return {
            "reply": reply,
            "cards": [],
            "suggestions": suggestions,
        }
    except Exception as e:
        return {
            "reply": f"抱歉，处理您的请求时出现了问题：{str(e)}",
            "cards": [],
            "suggestions": ["换个问法试试", "查询产品价格", "查看价格趋势"],
        }


async def chat_stream(message: str, conversation_id: str, enable_thinking: bool = False) -> AsyncGenerator[str, None]:
    """
    Streaming with optional thinking mode.

    SSE Events:
      - {"event": "thinking_token", "data": "x"}  Thinking process token
      - {"event": "token", "data": "x"}           Final answer token
      - {"event": "tool_start", "data": "name"}   Tool call started
      - {"event": "tool_end", "data": "name"}     Tool call ended
      - {"event": "done", "data": {...}}           Completion metadata
      - {"event": "error", "data": "x"}           Error
    """
    try:
        if enable_thinking:
            async for chunk in _stream_with_thinking(message, conversation_id):
                yield chunk
        else:
            async for chunk in _stream_normal(message, conversation_id):
                yield chunk

    except Exception as e:
        error_data = {"event": "error", "data": str(e)}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"


async def _stream_normal(message: str, conversation_id: str) -> AsyncGenerator[str, None]:
    """普通流式输出（Agent + 工具调用）"""
    yield f"data: {json.dumps({'event': 'thinking'}, ensure_ascii=False)}\n\n"

    usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    chat_history = _load_chat_history(conversation_id)
    user_scope = _build_user_scope_prompt()

    has_emitted_token = False
    last_tool_output = ""

    async for event in agent_executor.astream_events(
        {"input": message, "chat_history": chat_history, "user_scope": user_scope},
        version="v2",
    ):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                token = chunk.content
                if token:
                    has_emitted_token = True
                    yield f"data: {json.dumps({'event': 'token', 'data': token}, ensure_ascii=False)}\n\n"
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                um = chunk.usage_metadata
                usage_data["prompt_tokens"] += um.get("input_tokens", 0)
                usage_data["completion_tokens"] += um.get("output_tokens", 0)
                usage_data["total_tokens"] += um.get("total_tokens", 0)

        elif kind == "on_chat_model_end":
            output = event.get("data", {}).get("output")
            if output and hasattr(output, "usage_metadata") and output.usage_metadata:
                um = output.usage_metadata
                usage_data["prompt_tokens"] += um.get("input_tokens", 0)
                usage_data["completion_tokens"] += um.get("output_tokens", 0)
                usage_data["total_tokens"] += um.get("total_tokens", 0)

        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            yield f"data: {json.dumps({'event': 'tool_start', 'data': tool_name}, ensure_ascii=False)}\n\n"

        elif kind == "on_tool_end":
            tool_name = event.get("name", "")
            # 记录最后一次工具输出，用于无 token 兜底
            output = event.get("data", {}).get("output")
            if output is not None:
                try:
                    last_tool_output = str(output)[:600]
                except Exception:
                    pass
            yield f"data: {json.dumps({'event': 'tool_end', 'data': tool_name}, ensure_ascii=False)}\n\n"

    # 兜底：如果整个 agent 流程没产生过 token（max_iterations 触发等情况），
    # 用最后一次工具返回作为答复
    if not has_emitted_token:
        fallback = last_tool_output or "抱歉，没能从数据库找到匹配的结果。请尝试更具体的产品名或换个问法。"
        yield f"data: {json.dumps({'event': 'token', 'data': fallback}, ensure_ascii=False)}\n\n"

    # 完成
    done_data = {
        "event": "done",
        "data": {
            "suggestions": ["查询今日蔬菜价格", "对比不同品牌食用油价格", "查看近7天鸡蛋价格趋势"],
            "cards": [],
            "conversation_id": conversation_id,
            "usage": usage_data,
        }
    }
    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"


async def _stream_with_thinking(message: str, conversation_id: str) -> AsyncGenerator[str, None]:
    """
    思考模式流式输出：
    1. 先用 Agent（非流式）调用工具获取数据
    2. 将工具结果 + 用户问题一起发给 LLM（开启 thinking），流式输出思考过程和最终回答
    """
    yield f"data: {json.dumps({'event': 'tool_start', 'data': '分析问题'}, ensure_ascii=False)}\n\n"

    chat_history = _load_chat_history(conversation_id)
    user_scope = _build_user_scope_prompt()

    try:
        agent_result = await agent_executor.ainvoke({
            "input": message,
            "chat_history": chat_history,
            "user_scope": user_scope,
        })
        tool_output = agent_result.get("output") or _last_tool_observation(
            agent_result.get("intermediate_steps", [])
        )
    except Exception as e:
        tool_output = f"工具调用出错: {str(e)}"

    yield f"data: {json.dumps({'event': 'tool_end', 'data': '分析问题'}, ensure_ascii=False)}\n\n"

    # 阶段2：用思考模式深度分析
    thinking_prompt = f"""你是一个B端采销询价助手。

{user_scope}

用户问题：{message}

以下是通过工具查询到的数据：
{tool_output}

请基于以上数据，给用户一个专业、详细的回答。如果数据中有价格信息，请整理成清晰的格式；
如果数据显示无权访问，请直接告知用户没有该分类的查询权限。"""

    completion = await openai_client.chat.completions.create(
        model=settings.dashscope_model,
        messages=[{"role": "user", "content": thinking_prompt}],
        extra_body={"enable_thinking": True},
        stream=True,
        stream_options={"include_usage": True},
    )

    usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    has_emitted_token = False

    async for chunk in completion:
        if not chunk.choices:
            if hasattr(chunk, "usage") and chunk.usage:
                usage_data["prompt_tokens"] = chunk.usage.prompt_tokens or 0
                usage_data["completion_tokens"] = chunk.usage.completion_tokens or 0
                usage_data["total_tokens"] = chunk.usage.total_tokens or 0
            continue

        delta = chunk.choices[0].delta

        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            yield f"data: {json.dumps({'event': 'thinking_token', 'data': delta.reasoning_content}, ensure_ascii=False)}\n\n"

        if hasattr(delta, "content") and delta.content:
            has_emitted_token = True
            yield f"data: {json.dumps({'event': 'token', 'data': delta.content}, ensure_ascii=False)}\n\n"

    if not has_emitted_token:
        fallback = tool_output or "抱歉，没能从数据库找到匹配的结果。"
        yield f"data: {json.dumps({'event': 'token', 'data': fallback}, ensure_ascii=False)}\n\n"

    done_data = {
        "event": "done",
        "data": {
            "suggestions": ["查询今日蔬菜价格", "对比不同品牌食用油价格", "查看近7天鸡蛋价格趋势"],
            "cards": [],
            "conversation_id": conversation_id,
            "usage": usage_data,
        }
    }
    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
