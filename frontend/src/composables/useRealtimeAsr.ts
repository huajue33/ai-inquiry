import { ref, computed, onUnmounted } from "vue"
import { useMicCapture } from "./useMicCapture"
import { downsample, floatToPcm16, TARGET_SAMPLE_RATE } from "../utils/audio"

/**
 * 实时语音识别（边说边出字）。
 *
 * 麦克风采集复用 useMicCapture，逐帧重采样为 16kHz/16-bit PCM 后通过 WebSocket
 * 推给后端中继（/api/chat/asr-stream），后端转给百炼 Paraformer 实时识别，
 * 把中间/最终结果实时回传。`liveText` 为当前累计文本，可直接绑到界面。
 */
export function useRealtimeAsr() {
  const mic = useMicCapture()
  const isSupported = computed(() => mic.isSupported.value && typeof WebSocket !== "undefined")
  const isRecording = ref(false)
  const liveText = ref("")
  const errorMsg = ref("")

  let ws: WebSocket | null = null
  let committed = ""   // 已定稿的句子
  let interim = ""     // 当前识别中的句子
  let completeResolver: ((text: string) => void) | null = null

  function recompute() {
    liveText.value = committed + interim
  }

  function closeWs() {
    if (ws) {
      try {
        ws.onmessage = null
        ws.onerror = null
        ws.onclose = null
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close()
      } catch {
        /* ignore */
      }
      ws = null
    }
  }

  function buildWsUrl(): string {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    const token = localStorage.getItem("token") || ""
    return `${proto}//${window.location.host}/api/chat/asr-stream?token=${encodeURIComponent(token)}`
  }

  function openWs(): Promise<boolean> {
    return new Promise((resolve) => {
      try {
        ws = new WebSocket(buildWsUrl())
      } catch {
        resolve(false)
        return
      }
      const timer = setTimeout(() => resolve(false), 5000)
      ws.onopen = () => {
        clearTimeout(timer)
        resolve(true)
      }
      ws.onerror = () => {
        clearTimeout(timer)
        resolve(false)
      }
    })
  }

  function bindWsHandlers() {
    if (!ws) return
    ws.onmessage = (ev) => {
      let msg: any
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      if (msg.type === "result") {
        if (msg.end) {
          committed += msg.text
          interim = ""
        } else {
          interim = msg.text
        }
        recompute()
      } else if (msg.type === "complete") {
        completeResolver?.(liveText.value.trim())
        completeResolver = null
      } else if (msg.type === "error") {
        errorMsg.value = msg.message || "识别出错"
        completeResolver?.(liveText.value.trim())
        completeResolver = null
      }
    }
    ws.onclose = () => {
      // 服务端关闭：若还在等 complete，用当前文本兜底
      completeResolver?.(liveText.value.trim())
      completeResolver = null
    }
  }

  /** 开始实时识别，返回是否成功启动 */
  async function start(): Promise<boolean> {
    if (!isSupported.value) {
      errorMsg.value = "当前浏览器不支持录音"
      return false
    }
    if (isRecording.value) return false

    errorMsg.value = ""
    committed = ""
    interim = ""
    liveText.value = ""

    // 先建立 WebSocket（鉴权/连接失败可快速回退），再开始采集推流
    const opened = await openWs()
    if (!opened || !ws) {
      closeWs()
      errorMsg.value = "实时识别连接失败"
      return false
    }
    bindWsHandlers()

    const ok = await mic.start((frame) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      const pcm = floatToPcm16(downsample(frame, mic.getSampleRate(), TARGET_SAMPLE_RATE))
      ws.send(pcm.buffer as ArrayBuffer)
    })
    if (!ok) {
      closeWs()
      errorMsg.value = mic.errorMsg.value || "麦克风启动失败"
      return false
    }

    isRecording.value = true
    return true
  }

  /** 停止识别，等待最终结果并返回完整文本 */
  async function stop(): Promise<string> {
    if (!isRecording.value) return liveText.value.trim()
    isRecording.value = false

    // 停止采集（不再推新帧），但保持 ws 等待最终结果
    mic.stop()

    const finalText = await new Promise<string>((resolve) => {
      completeResolver = resolve
      try {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send("stop")
        else resolve(liveText.value.trim())
      } catch {
        resolve(liveText.value.trim())
      }
      // 兜底超时
      setTimeout(() => {
        if (completeResolver) {
          completeResolver(liveText.value.trim())
          completeResolver = null
        }
      }, 8000)
    })

    closeWs()
    return finalText
  }

  /** 中止，丢弃结果 */
  function abort() {
    isRecording.value = false
    completeResolver = null
    mic.stop()
    closeWs()
    committed = ""
    interim = ""
    liveText.value = ""
  }

  onUnmounted(() => abort())

  return { isSupported, isRecording, liveText, errorMsg, start, stop, abort }
}
