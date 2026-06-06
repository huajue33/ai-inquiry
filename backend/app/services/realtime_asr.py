"""实时语音识别中继。

浏览器通过 WebSocket 把麦克风 PCM 音频帧推给后端，后端用 DashScope SDK 的
Paraformer 实时识别（paraformer-realtime-v2）边推边收，把中间/最终结果实时回传前端。

API key 只在服务端持有，绝不下发到浏览器，因此必须由后端做中继。

DashScope SDK 的识别回调运行在其自己的后台线程，这里用 loop.call_soon_threadsafe
把结果安全地投递回 asyncio 事件循环对应的队列。
"""
import asyncio
import logging
from typing import Optional

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

ASR_MODEL = "paraformer-realtime-v2"
SAMPLE_RATE = 16000


class RealtimeAsrSession:
    """封装一次实时识别会话，桥接 SDK 回调线程与 asyncio。"""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self.queue: asyncio.Queue = asyncio.Queue()
        self._recognition: Optional[Recognition] = None

        outer = self

        class _Callback(RecognitionCallback):
            def on_event(self, result: RecognitionResult) -> None:
                try:
                    sentence = result.get_sentence()
                    if isinstance(sentence, dict) and sentence.get("text"):
                        outer._emit({
                            "type": "result",
                            "text": sentence["text"],
                            "end": RecognitionResult.is_sentence_end(sentence),
                        })
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"on_event 解析失败: {e}")

            def on_complete(self) -> None:
                outer._emit({"type": "complete"})

            def on_error(self, result) -> None:
                msg = getattr(result, "message", None) or str(result)
                outer._emit({"type": "error", "message": str(msg)})

            def on_close(self) -> None:
                outer._emit({"type": "closed"})

        self._callback = _Callback()

    def _emit(self, item: dict) -> None:
        """从任意线程安全地把结果投递到事件循环队列。"""
        self._loop.call_soon_threadsafe(self.queue.put_nowait, item)

    def start(self) -> None:
        """启动识别（阻塞调用，应放线程池执行）。"""
        dashscope.api_key = settings.dashscope_api_key
        self._recognition = Recognition(
            model=ASR_MODEL,
            format="pcm",
            sample_rate=SAMPLE_RATE,
            semantic_punctuation_enabled=False,  # VAD 分句，低延迟，适合交互
            callback=self._callback,
        )
        self._recognition.start()

    def send_frame(self, buffer: bytes) -> None:
        """推送一帧音频（阻塞调用，应放线程池执行）。"""
        if self._recognition is not None:
            self._recognition.send_audio_frame(buffer)

    def stop(self) -> None:
        """停止识别，阻塞直到服务端返回全部结果（应放线程池执行）。"""
        if self._recognition is not None:
            try:
                self._recognition.stop()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"停止识别异常: {e}")
            finally:
                self._recognition = None
