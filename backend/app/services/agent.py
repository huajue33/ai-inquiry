from functools import lru_cache

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from openai import AsyncOpenAI

from app.config import get_settings
from app.tools.price_tools import (
    search_products,
    get_latest_prices,
    get_price_history,
    get_price_ranking,
)
from app.tools.web_tools import web_search

settings = get_settings()


class ReasoningChatOpenAI(ChatOpenAI):
    """把 DashScope/Qwen 的 reasoning_content（思考过程）透出到 additional_kwargs。

    langchain-openai 的基类只解析 OpenAI 官方字段、默认不提取第三方的 reasoning_content
    （文档明确建议用 provider 专属子类）。这里重写 chunk 转换，在流式中把思考内容捞出来，
    使思考模式可在单次 agent 流式里同时拿到「思考 + 工具调用 + 回答」。
    """

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        gen = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if gen is None:
            return gen
        try:
            choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
            if choices:
                delta = choices[0].get("delta") or {}
                rc = delta.get("reasoning_content")
                if rc:
                    gen.message.additional_kwargs["reasoning_content"] = rc
        except Exception:
            pass
        return gen


# 原生 OpenAI 客户端（ASR 等直连调用；模型在调用时按需指定）
openai_client = AsyncOpenAI(
    api_key=settings.dashscope_api_key,
    base_url=settings.dashscope_base_url,
)

_price_tools = [
    search_products,
    get_latest_prices,
    get_price_history,
    get_price_ranking,
]
_all_tools = [*_price_tools, web_search]


def _build_llm(model: str, enable_thinking: bool = False):
    """按模型构建 LLM。enable_thinking=True 时用 ReasoningChatOpenAI 并开启思考。"""
    common = dict(
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
        model=model,
        streaming=True,
        model_kwargs={"stream_options": {"include_usage": True}},
    )
    if enable_thinking:
        return ReasoningChatOpenAI(extra_body={"enable_thinking": True}, **common)
    return ChatOpenAI(**common)


@lru_cache(maxsize=32)
def get_agents(model: str, enable_thinking: bool = False):
    """返回 (agent, agent_web) 二元组，按 (模型, 是否思考) 缓存，避免每请求重建。

    - agent：仅价格工具
    - agent_web：价格工具 + 联网搜索
    """
    llm = _build_llm(model, enable_thinking)
    return (
        create_agent(llm, _price_tools),
        create_agent(llm, _all_tools),
    )
