"""语音识别（ASR）服务。

复用现有的 OpenAI 兼容客户端调用百炼 qwen3-asr-flash 模型，把上传的音频转成文字。
前端录音统一编码为 WAV（PCM），这里以 base64 data URI 形式传给模型，无需 OSS。
"""
import base64
import logging

from app.config import get_settings
from app.services.agent import openai_client

logger = logging.getLogger(__name__)
settings = get_settings()

# 上传音频大小上限（约 10MB，nginx client_max_body_size 为 20m）
MAX_AUDIO_BYTES = 10 * 1024 * 1024


async def transcribe(audio_bytes: bytes, audio_format: str = "wav") -> str:
    """把音频字节转写为文字。

    Args:
        audio_bytes: 音频二进制内容
        audio_format: 音频格式（wav/mp3 等），用于构造 data URI 的 MIME

    Returns:
        识别出的文本（去除首尾空白）。无结果时返回空串。
    """
    if not audio_bytes:
        return ""
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("音频过大，请缩短录音时长")

    b64 = base64.b64encode(audio_bytes).decode("ascii")
    data_uri = f"data:audio/{audio_format};base64,{b64}"

    completion = await openai_client.chat.completions.create(
        model=settings.dashscope_asr_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": data_uri}},
                ],
            }
        ],
        extra_body={"asr_options": {"enable_itn": True}},
    )

    content = completion.choices[0].message.content if completion.choices else ""
    if isinstance(content, list):
        # 兼容多模态返回为 content 数组的情况
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return (content or "").strip()
