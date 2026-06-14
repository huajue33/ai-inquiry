import json
import logging
import re
import time
from datetime import date
from typing import AsyncGenerator

from starlette.concurrency import run_in_threadpool
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.errors import GraphRecursionError

from app.core.prompts import SYSTEM_PROMPT
from app.core.permissions import current_user_var
from app.core.models import route_model, model_supports_thinking
from app.database import SessionLocal
from app.models.product import Category
from app.models.permission import UserCategoryPermission
from app.services.agent import get_agent
from app.services.history import load_history
from app.services.persistence import save_assistant_message

logger = logging.getLogger(__name__)

# Agent 图递归上限（兜底；工具层已对 search_products 限次，这里防其他失控）
AGENT_RECURSION_LIMIT = 15

# 每次工具调用结果存库时的单条上限（防止超大返回撑爆行；仅影响后台展示，不影响推理）
TOOL_RESULT_MAX_CHARS = 20000

# 每轮结束给前端的快捷建议（固定文案，多处复用）
DEFAULT_SUGGESTIONS = ["查询今日蔬菜价格", "对比不同品牌食用油价格", "查看近7天鸡蛋价格趋势"]


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


# ── 决策日志（本地可观测性） ──────────────────────────

def _tool_outcome(output) -> str:
    """从工具输出粗略判定状态：error:<code> / empty / ok。"""
    try:
        s = str(output)
    except Exception:
        return "ok"
    m = re.search(r'"error"\s*:\s*"([^"]+)"', s)
    if m:
        return f"error:{m.group(1)}"
    if re.search(r'"(total|returned)"\s*:\s*0\b', s):
        return "empty"
    return "ok"


def _log_trace(acc: dict, model: str, thinking: bool, duration_ms: int, outcome: str) -> None:
    """每轮对话收尾打一条结构化决策日志，便于本地排障（无外部依赖）。"""
    try:
        user = current_user_var.get()
        tools = acc.get("tool_calls", [])
        tool_str = ", ".join(
            f"{t['tool']}({str(t.get('args', {}))[:50]})->{t['status']}/{t.get('duration_ms', '?')}ms"
            for t in tools
        ) or "-"
        usage = acc.get("usage", {})
        logger.info(
            "[agent-trace] user=%s model=%s thinking=%s web=%s tools=[%s] tokens=%s dur=%dms outcome=%s",
            getattr(user, "id", None), model, thinking, acc.get("web_used", False),
            tool_str, usage.get("total_tokens", 0), duration_ms, outcome,
        )
    except Exception:
        pass


# ── 运行时上下文 ────────────────────────────────────────

def _build_runtime_context() -> str:
    """构建运行时上下文信息，包含当前日期和用户权限范围"""
    today = date.today()
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
    date_line = f"当前日期：{today.isoformat()}（{weekday}）。"

    user = current_user_var.get()
    if user is None:
        return date_line + "\n当前匿名访问，没有数据查询权限。"

    role_cn = {"admin": "管理员", "manager": "主管", "buyer": "采购员"}.get(user.role, user.role)

    if user.role in ("admin", "manager"):
        return (
            date_line
            + f"\n当前用户：{user.real_name}（{role_cn}），可访问全部分类。"
            "若用户问“我是谁”之类，用其姓名和中文角色回答，不要暴露英文角色代码。"
        )

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

async def chat_stream(message: str, conversation_id: str, enable_thinking: bool = False, model: str | None = None) -> AsyncGenerator[str, None]:
    """根据模式分派到常规流式或思考流式，以SSE格式输出AI回复。

    无论正常结束还是客户端中途断开（关闭页面/点停止），都会在 finally 中由服务端
    兜底持久化助手消息，内容/思考/usage/duration 以服务端为准。
    """
    # 解析实际调用的模型：auto 时按问题复杂度路由到 lite/主模型；否则尊重用户选择
    model = route_model(model, message)
    # 仅当模型支持思考时才真正开启（避免对不支持的模型发 enable_thinking）
    thinking = bool(enable_thinking) and model_supports_thinking(model)

    # 累加器：内层函数边产出边写入，供流结束后持久化
    acc = {
        "content": "",
        "thinking": "",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "suggestions": [],
        "tool_calls": [],
        "web_used": False,
    }
    user = current_user_var.get()
    started_at = time.monotonic()
    outcome = "ok"

    try:
        async for chunk in _stream(message, conversation_id, acc, model, thinking):
            yield chunk

    except GraphRecursionError:
        # 兜底：Agent 反复调用工具未收敛（如查询数据库里不存在的商品）。
        # 给用户一个干净的回答而非原始报错，并作为正常内容持久化。
        outcome = "recursion_limit"
        fallback = acc.get("content") or "抱歉，没能找到相关商品，可能暂未收录。换个名称或确认是否在售再试试。"
        if not acc.get("content"):
            acc["content"] = fallback
            yield f"data: {json.dumps({'event': 'token', 'data': fallback}, ensure_ascii=False)}\n\n"
        done_data = {
            "event": "done",
            "data": {
                "suggestions": DEFAULT_SUGGESTIONS,
                "conversation_id": conversation_id,
                "usage": acc.get("usage", {}),
                "content": acc["content"],
            },
        }
        yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"

    except Exception as e:
        outcome = "error"
        error_data = {"event": "error", "data": str(e)}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    finally:
        # 同步落库：finally 在协程被取消（客户端断开）时仍会执行，
        # 这里不做 await，避免在取消阶段再次被取消而中断写入。
        duration_ms = int((time.monotonic() - started_at) * 1000)
        if outcome == "ok" and not acc.get("content"):
            outcome = "empty"
        _log_trace(acc, model, thinking, duration_ms, outcome)
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
                    tool_trace=acc.get("tool_calls"),
                )
            except Exception as e:
                logger.warning(f"流结束时持久化助手消息失败: {e}")


async def _stream(message: str, conversation_id: str, acc: dict, model: str, thinking: bool) -> AsyncGenerator[str, None]:
    """统一的单次流式：LangGraph Agent + 工具调用（+ 可选思考）。

    thinking=True 时使用开启 reasoning 的 Agent，在同一次流式里同时产出
    思考过程（thinking_token）、工具调用与最终回答，无需两段式。
    """
    usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    _agent = get_agent(model, thinking)

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

    async for event in _agent.astream_events(
        {"messages": messages}, version="v2", config={"recursion_limit": AGENT_RECURSION_LIMIT}
    ):
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
            acc.setdefault("tool_calls", []).append({
                "tool": tool_name,
                "args": event.get("data", {}).get("input", {}),
                "status": "?",
                "_t0": time.monotonic(),
            })
            yield f"data: {json.dumps({'event': 'tool_start', 'data': tool_name}, ensure_ascii=False)}\n\n"

        elif kind == "on_tool_end":
            tool_name = event.get("name", "")
            output = event.get("data", {}).get("output")
            out_str = ""
            if output is not None:
                try:
                    # ToolMessage 取 .content，其余直接 str()
                    out_str = getattr(output, "content", None)
                    if out_str is None:
                        out_str = str(output)
                    last_tool_output = out_str[:600]
                    all_tool_outputs.append(out_str)
                except Exception:
                    out_str = ""
            # 记录工具结果状态 + 完整返回（截断）到轨迹（用于决策日志 / 后台执行流程展示）
            status = _tool_outcome(output)
            for entry in reversed(acc.get("tool_calls", [])):
                if entry["tool"] == tool_name and entry["status"] == "?":
                    entry["status"] = status
                    entry["result"] = out_str[:TOOL_RESULT_MAX_CHARS]
                    t0 = entry.pop("_t0", None)
                    if t0 is not None:
                        entry["duration_ms"] = int((time.monotonic() - t0) * 1000)
                    break
            if tool_name == "web_search":
                acc["web_used"] = True
            yield f"data: {json.dumps({'event': 'tool_end', 'data': tool_name}, ensure_ascii=False)}\n\n"

    if not has_emitted_token:
        fallback = last_tool_output or "抱歉，没能从数据库找到匹配的结果。请尝试更具体的产品名或换个问法。"
        acc["content"] = acc.get("content", "") + fallback
        yield f"data: {json.dumps({'event': 'token', 'data': fallback}, ensure_ascii=False)}\n\n"

    # 清理轨迹里可能残留的临时计时字段（无对应 tool_end 的调用）
    for entry in acc.get("tool_calls", []):
        entry.pop("_t0", None)

    # 剥离幻觉的 {#id=N} 标记（不在本轮工具结果/历史中的 ID）
    valid_ids = _collect_valid_ids(history, "\n".join(all_tool_outputs))
    acc["content"] = _scrub_invalid_id_markers(acc.get("content", ""), valid_ids)

    suggestions = DEFAULT_SUGGESTIONS
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
