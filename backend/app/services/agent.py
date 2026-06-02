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

# LangChain LLM（工具调用 + 常规回复）
llm = ChatOpenAI(
    base_url=settings.dashscope_base_url,
    api_key=settings.dashscope_api_key,
    model=settings.dashscope_model,
    streaming=True,
    model_kwargs={"stream_options": {"include_usage": True}},
)

# 原生 OpenAI 客户端（思考模式直接调用）
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

# 两个 Agent 实例：根据用户是否开启联网搜索来选择
agent = create_react_agent(llm, _price_tools)
agent_web = create_react_agent(llm, _all_tools)
