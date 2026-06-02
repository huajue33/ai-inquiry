import httpx

from langchain_core.tools import tool

from app.config import get_settings

DASHSCOPE_GEN_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"


@tool
async def web_search(query: str) -> str:
    """搜索互联网获取最新的市场信息、新闻动态、政策变化等实时信息。

    当用户询问市场行情、价格走势、行业新闻、政策变动等需要联网获取最新信息时调用。
    日常的价格查询用 search_products / get_latest_prices 即可，不需要此工具。
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                DASHSCOPE_GEN_URL,
                headers={
                    "Authorization": f"Bearer {settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen-plus",
                    "input": {
                        "messages": [{"role": "user", "content": query}],
                    },
                    "parameters": {
                        "enable_search": True,
                        "result_format": "message",
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["output"]["choices"][0]["message"].get("content", "")
        if not content:
            return "【搜索结果】搜索暂无结果，建议换个关键词重试。"
        return f"【搜索结果】\n{content}"
    except Exception as e:
        return f"【搜索结果】搜索失败：{str(e)}"
