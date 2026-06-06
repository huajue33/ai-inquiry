import json
import logging
import re
import time
from datetime import date
from typing import AsyncGenerator

from starlette.concurrency import run_in_threadpool
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.prompts import SYSTEM_PROMPT
from app.core.permissions import current_user_var
from app.core.models import resolve_model, model_supports_thinking
from app.database import SessionLocal
from app.models.product import Category
from app.models.permission import UserCategoryPermission
from app.services.agent import get_agents
from app.services.history import load_history
from app.services.persistence import save_assistant_message

logger = logging.getLogger(__name__)


# ── 产品 ID 标记校验（防幻觉链接） ──────────────────────

_PRODUCT_ID_RE = re.compile(r'"product_id"\s*:\s*(\d+)')
# 兼容模型可能输出的单括号 {#id=N} 或双括号 {{#id=N}}
_ID_MARKER_RE = re.compile(r"\{{1,2}#id=(\d+)\}{1,2}")


def _collect_valid_ids(history, tool_output: str) -> set[int]:
    """收集本轮"可信"的 product_id 集合：

    - 本轮工具返回结果中的 product_id（"product_id": N）
    - 历史消息文本中出现过的 product_id 与 {#id=N} 标记

    历史也纳入，避免误删"复用上一轮 ID"（如用户说"第二个"）的合法链接。
    """
    valid: set[int] = set()
    for m in history or []:
        content = getattr(m, "content", "")
        if isinstance(content, str) and content:
            valid.update(int(x) for x in _PRODUCT_ID_RE.findall(content))
            valid.update(int(x) for x in _ID_MARKER_RE.findall(content))
    if tool_output:
        valid.update(int(x) for x in _PRODUCT_ID_RE.findall(tool_output))
    return valid


def _scrub_invalid_id_markers(content: str, valid_ids: set[int]) -> str:
    """归一化 {#id=N} 标记并剥离幻觉链接：

    - 统一把单/双括号归一化为单括号 `{#id=N}`（修正模型偶发的双括号，否则前端会渲染出 `{}`）。
    - valid_ids 非空时，剥离其中不可信的 id（既不在本轮工具结果、也不在历史里）。
    - **valid_ids 为空时 fail-open**：只归一化、不删除，避免在收集失败/纯对话场景误删合法链接。
    """
    if not content:
        return content

    def _repl(match: "re.Match") -> str:
        pid = int(match.group(1))
        if valid_ids and pid not in valid_ids:
            return ""  # 确认为编造的 ID → 去掉标记（保留前面的文字）
        return "{#id=%d}" % pid  # 归一化为单括号

    return _ID_MARKER_RE.sub(_repl, content)


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

async def chat_stream(message: str, conversation_id: str, enable_thinking: bool = False, enable_web_search: bool = False, model: str | None = None) -> AsyncGenerator[str, None]:
    """根据模式分派到常规流式或思考流式，以SSE格式输出AI回复。

    无论正常结束还是客户端中途断开（关闭页面/点停止），都会在 finally 中由服务端
    兜底持久化助手消息，内容/思考/usage/duration 以服务端为准。
    """
    # 模型收敛为白名单内的合法值（非法/缺省回退默认模型）
    model = resolve_model(model)
    # 仅当模型支持思考时才真正开启（避免对不支持的模型发 enable_thinking）
    thinking = bool(enable_thinking) and model_supports_thinking(model)

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
        async for chunk in _stream(message, conversation_id, enable_web_search, acc, model, thinking):
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


async def _stream(message: str, conversation_id: str, enable_web_search: bool, acc: dict, model: str, thinking: bool) -> AsyncGenerator[str, None]:
    """统一的单次流式：LangGraph Agent + 工具调用（+ 可选思考）。

    thinking=True 时使用开启 reasoning 的 Agent，在同一次流式里同时产出
    思考过程（thinking_token）、工具调用与最终回答，无需两段式。
    """
    usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    agent, agent_web = get_agents(model, thinking)
    _agent = agent_web if enable_web_search else agent

    # 同步 DB 查询放线程池，避免阻塞事件循环
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
    all_tool_outputs: list[str] = []

    async for event in _agent.astream_events({"messages": messages}, version="v2"):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]

            # 思考过程（reasoning_content 由 ReasoningChatOpenAI 透出到 additional_kwargs）
            rc = getattr(chunk, "additional_kwargs", {}).get("reasoning_content")
            if rc:
                acc["thinking"] = acc.get("thinking", "") + rc
                yield f"data: {json.dumps({'event': 'thinking_token', 'data': rc}, ensure_ascii=False)}\n\n"

            token = getattr(chunk, "content", "")
            if token:
                has_emitted_token = True
                acc["content"] = acc.get("content", "") + token
                yield f"data: {json.dumps({'event': 'token', 'data': token}, ensure_ascii=False)}\n\n"

            if getattr(chunk, "usage_metadata", None):
                um = chunk.usage_metadata
                usage_data["prompt_tokens"] += um.get("input_tokens", 0)
                usage_data["completion_tokens"] += um.get("output_tokens", 0)
                usage_data["total_tokens"] += um.get("total_tokens", 0)

        elif kind == "on_chat_model_end":
            output = event.get("data", {}).get("output")
            if output and getattr(output, "usage_metadata", None):
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
                    out_str = str(output)
                    last_tool_output = out_str[:600]
                    all_tool_outputs.append(out_str)
                except Exception:
                    pass
            yield f"data: {json.dumps({'event': 'tool_end', 'data': tool_name}, ensure_ascii=False)}\n\n"

    if not has_emitted_token:
        fallback = last_tool_output or "抱歉，没能从数据库找到匹配的结果。请尝试更具体的产品名或换个问法。"
        acc["content"] = acc.get("content", "") + fallback
        yield f"data: {json.dumps({'event': 'token', 'data': fallback}, ensure_ascii=False)}\n\n"

    # 剥离幻觉的 {#id=N} 标记（不在本轮工具结果/历史中的 ID）
    valid_ids = _collect_valid_ids(history, "\n".join(all_tool_outputs))
    acc["content"] = _scrub_invalid_id_markers(acc.get("content", ""), valid_ids)

    suggestions = ["查询今日蔬菜价格", "对比不同品牌食用油价格", "查看近7天鸡蛋价格趋势"]
    acc["usage"] = usage_data
    acc["suggestions"] = suggestions

    done_data = {
        "event": "done",
        "data": {
            "suggestions": suggestions,
            "conversation_id": conversation_id,
            "usage": usage_data,
            "content": acc["content"],
        }
    }
    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
