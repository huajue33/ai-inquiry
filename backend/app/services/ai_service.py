import json
import logging
import time
from datetime import date
from typing import AsyncGenerator

from starlette.concurrency import run_in_threadpool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from app.config import get_settings
from app.core.prompts import SYSTEM_PROMPT
from app.core.permissions import current_user_var
from app.database import SessionLocal
from app.models.product import Category
from app.models.permission import UserCategoryPermission
from app.services.agent import agent, agent_web, openai_client
from app.services.history import load_history
from app.services.persistence import save_assistant_message

logger = logging.getLogger(__name__)
settings = get_settings()


# ── 运行时上下文 ────────────────────────────────────────

def _build_runtime_context() -> str:
    """构建运行时上下文信息，包含当前日期和用户权限范围"""
    today = date.today()
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
    date_line = f"当前日期：{today.isoformat()}（{weekday}）。"

    user = current_user_var.get()
    if user is None:
        return date_line + "\n当前匿名访问，没有数据查询权限。"

    if user.role in ("admin", "manager"):
        return date_line + f"\n当前用户角色 {user.role}，可访问全部分类。"

    db = SessionLocal()
    try:
        rows = (
            db.query(Category.name)
            .join(
                UserCategoryPermission,
                UserCategoryPermission.category_id == Category.id,
            )
            .filter(UserCategoryPermission.user_id == user.id)
            .all()
        )
        if not rows:
            return (
                date_line
                + f"\n当前用户 {user.real_name}（采购员）未被授权任何分类。"
                "直接告知用户'你当前没有数据查询权限，请联系管理员授权'，不要调用任何工具。"
            )

        allowed = "、".join(r[0] for r in rows)
        return (
            date_line
            + f"\n当前用户 {user.real_name}（采购员），可访问的二级分类：{allowed}。"
            "其他分类工具会返回 permission_denied，按错误信息回复即可。"
        )
    finally:
        db.close()


# ── 流式入口 ────────────────────────────────────────────

async def chat_stream(message: str, conversation_id: str, enable_thinking: bool = False, enable_web_search: bool = False) -> AsyncGenerator[str, None]:
    """根据模式分派到常规流式或思考流式，以SSE格式输出AI回复。

    无论正常结束还是客户端中途断开（关闭页面/点停止），都会在 finally 中由服务端
    兜底持久化助手消息，内容/思考/usage/duration 以服务端为准。
    """
    # 累加器：内层函数边产出边写入，供流结束后持久化
    acc = {
        "content": "",
        "thinking": "",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "suggestions": [],
    }
    user = current_user_var.get()
    started_at = time.monotonic()

    try:
        if enable_thinking:
            async for chunk in _stream_with_thinking(message, conversation_id, enable_web_search, acc):
                yield chunk
        else:
            async for chunk in _stream_normal(message, conversation_id, enable_web_search, acc):
                yield chunk

    except Exception as e:
        error_data = {"event": "error", "data": str(e)}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    finally:
        # 同步落库：finally 在协程被取消（客户端断开）时仍会执行，
        # 这里不做 await，避免在取消阶段再次被取消而中断写入。
        duration_ms = int((time.monotonic() - started_at) * 1000)
        if user is not None and (acc["content"] or acc["thinking"]):
            try:
                save_assistant_message(
                    conversation_id=conversation_id,
                    user_id=user.id,
                    content=acc["content"],
                    thinking=acc["thinking"],
                    suggestions=acc["suggestions"],
                    duration_ms=duration_ms,
                    usage=acc["usage"],
                )
            except Exception as e:
                logger.warning(f"流结束时持久化助手消息失败: {e}")


async def _stream_normal(message: str, conversation_id: str, enable_web_search: bool = False, acc: dict = None) -> AsyncGenerator[str, None]:
    """普通流式输出：LangGraph Agent + 工具调用"""
    if acc is None:
        acc = {}
    usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    _agent = agent_web if enable_web_search else agent
    # 这两个调用内部是同步 DB 查询（load_history 还可能触发同步的摘要 LLM 调用），
    # 放进线程池执行，避免阻塞事件循环影响并发。
    history = await run_in_threadpool(load_history, conversation_id)
    runtime_context = await run_in_threadpool(_build_runtime_context)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content=runtime_context),
        *history,
        HumanMessage(content=message),
    ]

    has_emitted_token = False
    last_tool_output = ""

    async for event in _agent.astream_events(
        {"messages": messages}, version="v2"
    ):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                token = chunk.content
                if token:
                    has_emitted_token = True
                    acc["content"] = acc.get("content", "") + token
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
            output = event.get("data", {}).get("output")
            if output is not None:
                try:
                    last_tool_output = str(output)[:600]
                except Exception:
                    pass
            yield f"data: {json.dumps({'event': 'tool_end', 'data': tool_name}, ensure_ascii=False)}\n\n"

    if not has_emitted_token:
        fallback = last_tool_output or "抱歉，没能从数据库找到匹配的结果。请尝试更具体的产品名或换个问法。"
        acc["content"] = acc.get("content", "") + fallback
        yield f"data: {json.dumps({'event': 'token', 'data': fallback}, ensure_ascii=False)}\n\n"

    suggestions = ["查询今日蔬菜价格", "对比不同品牌食用油价格", "查看近7天鸡蛋价格趋势"]
    acc["usage"] = usage_data
    acc["suggestions"] = suggestions

    done_data = {
        "event": "done",
        "data": {
            "suggestions": suggestions,
            "conversation_id": conversation_id,
            "usage": usage_data,
        }
    }
    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"


async def _stream_with_thinking(message: str, conversation_id: str, enable_web_search: bool = False, acc: dict = None) -> AsyncGenerator[str, None]:
    """思考模式：Agent 收集工具数据 → 思考 LLM 深度分析"""
    if acc is None:
        acc = {}
    yield f"data: {json.dumps({'event': 'tool_start', 'data': '分析问题'}, ensure_ascii=False)}\n\n"

    _agent = agent_web if enable_web_search else agent
    # 同上：同步 DB / 摘要调用放线程池，避免阻塞事件循环。
    history = await run_in_threadpool(load_history, conversation_id)
    runtime_context = await run_in_threadpool(_build_runtime_context)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content=runtime_context),
        *history,
        HumanMessage(content=message),
    ]

    try:
        state = await _agent.ainvoke({"messages": messages})
        tool_output = "\n".join(
            msg.content[:600] for msg in state["messages"]
            if isinstance(msg, ToolMessage)
        ) or next((msg.content for msg in reversed(state["messages"])
                   if isinstance(msg, AIMessage) and msg.content), "")
    except Exception as e:
        tool_output = f"工具调用出错: {str(e)}"

    yield f"data: {json.dumps({'event': 'tool_end', 'data': '分析问题'}, ensure_ascii=False)}\n\n"

    thinking_prompt = f"""你是一个B端采销询价助手。

{runtime_context}

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
            acc["thinking"] = acc.get("thinking", "") + delta.reasoning_content
            yield f"data: {json.dumps({'event': 'thinking_token', 'data': delta.reasoning_content}, ensure_ascii=False)}\n\n"

        if hasattr(delta, "content") and delta.content:
            has_emitted_token = True
            acc["content"] = acc.get("content", "") + delta.content
            yield f"data: {json.dumps({'event': 'token', 'data': delta.content}, ensure_ascii=False)}\n\n"

    if not has_emitted_token:
        fallback = tool_output or "抱歉，没能从数据库找到匹配的结果。"
        acc["content"] = acc.get("content", "") + fallback
        yield f"data: {json.dumps({'event': 'token', 'data': fallback}, ensure_ascii=False)}\n\n"

    suggestions = ["查询今日蔬菜价格", "对比不同品牌食用油价格", "查看近7天鸡蛋价格趋势"]
    acc["usage"] = usage_data
    acc["suggestions"] = suggestions

    done_data = {
        "event": "done",
        "data": {
            "suggestions": suggestions,
            "conversation_id": conversation_id,
            "usage": usage_data,
        }
    }
    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
