from functools import lru_cache

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
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

# 原生 OpenAI 客户端（思考模式直接调用；模型在调用时按需指定）
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


def _build_llm(model: str) -> ChatOpenAI:
    """按模型构建 LangChain LLM（工具调用 + 常规回复）。"""
    return ChatOpenAI(
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
        model=model,
        streaming=True,
        model_kwargs={"stream_options": {"include_usage": True}},
    )


@lru_cache(maxsize=16)
def get_agents(model: str):
    """返回 (agent, agent_web) 二元组，按模型缓存，避免每请求重建。

    - agent：仅价格工具
    - agent_web：价格工具 + 联网搜索
    """
    llm = _build_llm(model)
    return (
        create_react_agent(llm, _price_tools),
        create_react_agent(llm, _all_tools),
    )
