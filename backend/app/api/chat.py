import asyncio
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from jose import JWTError

from app.schemas.chat import ChatRequest
from app.services import ai_service, asr_service
from app.services.realtime_asr import RealtimeAsrSession
from app.models.user import User
from app.database import SessionLocal
from app.core.security import get_current_user, decode_token
from app.core.permissions import current_user_var
from app.core.models import get_available_models, get_default_model
from app.tools.price_tools import reset_permission_cache

router = APIRouter()


def _authenticate_token(token: str) -> User | None:
    """WebSocket 手动鉴权：用 access token 换取用户（失败返回 None，不抛异常）。"""
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") == "refresh":
            return None
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user or not user.is_active:
            return None
        return user
    finally:
        db.close()


@router.get("/models")
async def list_models(user: User = Depends(get_current_user)):
    """返回前端可选的模型列表及默认模型。"""
    return {
        "models": get_available_models(),
        "default": get_default_model(),
    }


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """语音转写：接收上传的音频（前端录制的 WAV），返回识别文本。"""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频为空")

    # 从文件名/Content-Type 推断格式，默认 wav
    fmt = "wav"
    if file.filename and "." in file.filename:
        fmt = file.filename.rsplit(".", 1)[-1].lower()
    elif file.content_type and "/" in file.content_type:
        fmt = file.content_type.split("/", 1)[-1].lower()

    try:
        text = await asr_service.transcribe(audio_bytes, fmt)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"语音识别失败：{e}")

    return {"text": text}


@router.websocket("/asr-stream")
async def asr_stream(websocket: WebSocket):
    """实时语音识别（WebSocket）。

    协议：
    - 鉴权：连接 URL 带 ?token=<access_token>。
    - 客户端发送二进制帧 = 16kHz/单声道/16-bit PCM 音频。
    - 客户端发送文本 "stop" = 结束本次识别。
    - 服务端推送 JSON：
        {"type":"result","text":"...","end":bool}  中间/最终识别结果
        {"type":"complete"}                         全部识别完成
        {"type":"error","message":"..."}            出错
    """
    token = websocket.query_params.get("token", "")
    user = _authenticate_token(token)
    if user is None:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    loop = asyncio.get_running_loop()
    session = RealtimeAsrSession(loop)

    async def forward_results():
        """把识别结果队列里的内容转发给浏览器。"""
        while True:
            item = await session.queue.get()
            try:
                await websocket.send_json(item)
            except Exception:
                break
            if item.get("type") in ("complete", "error"):
                break

    try:
        await loop.run_in_executor(None, session.start)
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": f"识别启动失败：{e}"})
        finally:
            await websocket.close()
        return

    forward_task = asyncio.create_task(forward_results())

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data:
                await loop.run_in_executor(None, session.send_frame, data)
                continue
            text = message.get("text")
            if text == "stop":
                break
    except WebSocketDisconnect:
        pass
    finally:
        # stop() 阻塞直到服务端返回完整结果，放线程池执行
        try:
            await loop.run_in_executor(None, session.stop)
        except Exception:
            pass
        # 给转发任务一点时间把 complete 事件发出去
        try:
            await asyncio.wait_for(forward_task, timeout=5)
        except Exception:
            forward_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/stream")
async def chat_stream(request: ChatRequest, user: User = Depends(get_current_user)):
    """流式接口 - SSE（支持思考模式）"""
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # 把 user 也带给生成器（StreamingResponse 内的迭代发生在另一个上下文，
    # 需要在生成器内部重新 set 一次 ContextVar）
    async def event_generator():
        token = current_user_var.set(user)
        reset_permission_cache()
        try:
            async for chunk in ai_service.chat_stream(
                request.message, conversation_id, request.enable_thinking,
                request.enable_web_search, request.model,
            ):
                yield chunk
        finally:
            current_user_var.reset(token)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
