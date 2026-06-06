import { ref, onUnmounted } from "vue"

/**
 * 麦克风采集原语：封装 getUserMedia + Web Audio 的采集装配与清理。
 *
 * 通过 start(onFrame) 注册帧回调，每段音频（Float32，源采样率）通过回调送出。
 * useAudioRecorder（攒帧编 WAV）与 useRealtimeAsr（逐帧推流）共用本原语，
 * 各自决定如何处理帧，避免重复的麦克风装配代码。
 */
export function useMicCapture() {
  const isSupported = ref(
    typeof navigator !== "undefined" &&
      !!navigator.mediaDevices?.getUserMedia &&
      !!(window.AudioContext || (window as any).webkitAudioContext)
  )
  const isCapturing = ref(false)
  const errorMsg = ref("")

  let stream: MediaStream | null = null
  let audioCtx: AudioContext | null = null
  let source: MediaStreamAudioSourceNode | null = null
  let processor: ScriptProcessorNode | null = null
  let sourceSampleRate = 44100

  /** 源采样率（start 之后有效，stop 后仍保留供编码使用） */
  function getSampleRate(): number {
    return sourceSampleRate
  }

  /**
   * 开始采集。onFrame 收到的是每段音频的 Float32 拷贝（源采样率、单声道）。
   * 返回是否成功（失败时 errorMsg 给出原因）。
   */
  async function start(onFrame: (frame: Float32Array) => void): Promise<boolean> {
    if (!isSupported.value) {
      errorMsg.value = "当前浏览器不支持录音"
      return false
    }
    if (isCapturing.value) return false

    errorMsg.value = ""
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      errorMsg.value = "请允许浏览器使用麦克风"
      return false
    }

    const Ctx = window.AudioContext || (window as any).webkitAudioContext
    audioCtx = new Ctx()
    sourceSampleRate = audioCtx.sampleRate
    source = audioCtx.createMediaStreamSource(stream)
    processor = audioCtx.createScriptProcessor(4096, 1, 1)

    processor.onaudioprocess = (e: AudioProcessingEvent) => {
      // getChannelData 返回的视图会被复用，必须拷贝后再交出去
      onFrame(new Float32Array(e.inputBuffer.getChannelData(0)))
    }

    source.connect(processor)
    processor.connect(audioCtx.destination)
    isCapturing.value = true
    return true
  }

  /** 停止采集并释放资源 */
  function stop() {
    isCapturing.value = false
    try {
      processor?.disconnect()
      source?.disconnect()
    } catch {
      /* ignore */
    }
    if (audioCtx && audioCtx.state !== "closed") audioCtx.close().catch(() => {})
    stream?.getTracks().forEach((t) => t.stop())
    processor = null
    source = null
    audioCtx = null
    stream = null
  }

  onUnmounted(() => stop())

  return { isSupported, isCapturing, errorMsg, start, stop, getSampleRate }
}
