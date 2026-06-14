"""
用轻量模型生成对话标题
"""
import logging
from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=settings.dashscope_api_key,
    base_url=settings.dashscope_base_url,
    max_retries=settings.llm_max_retries,
)


async def generate_title(user_message: str) -> str:
    """
    根据用户第一条消息生成简短的对话标题（使用副模型节约成本）
    """
    # 如果消息太短或无意义，直接用消息本身
    if len(user_message.strip()) <= 2:
        return user_message.strip() or "新对话"

    try:
        response = await client.chat.completions.create(
            model=settings.dashscope_lite_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个标题生成器。根据用户发送的采购询价相关消息，生成一个简短的对话标题（不超过15个字）。直接输出标题，不要加引号、标点或解释。如果消息内容不明确，就直接概括消息内容。",
                },
                {"role": "user", "content": user_message},
            ],
            max_tokens=30,
        )
        title = response.choices[0].message.content.strip()
        # 去掉可能的引号和多余标点
        title = title.strip('"\'""''《》')
        if len(title) > 20:
            title = title[:20]
        return title or user_message[:15]
    except Exception as e:
        logger.warning(f"生成标题失败: {e}")
        return user_message[:15]
