import { ref, onUnmounted } from "vue"
import { useMicCapture } from "./useMicCapture"
import { mergeChunks, downsample, encodeWav, TARGET_SAMPLE_RATE } from "../utils/audio"

/**
 * 一次性录音 → 16kHz 单声道 16-bit PCM WAV。
 *
 * 用于"录完整段再上传识别"的兜底方案（实时识别连接失败时回退）。
 * 麦克风采集复用 useMicCapture，音频处理复用 utils/audio。
 */
export function useAudioRecorder() {
  const mic = useMicCapture()
  const isRecording = ref(false)
  let chunks: Float32Array[] = []

  /** 开始录音，返回是否成功 */
  async function start(): Promise<boolean> {
    if (isRecording.value) return false
    chunks = []
    const ok = await mic.start((frame) => chunks.push(frame))
    isRecording.value = ok
    return ok
  }

  /** 停止录音并返回 WAV Blob（无音频时返回 null） */
  async function stop(): Promise<Blob | null> {
    if (!isRecording.value) return null
    isRecording.value = false

    const sr = mic.getSampleRate()
    mic.stop()

    const recorded = chunks
    chunks = []
    const merged = mergeChunks(recorded)
    if (merged.length === 0) return null

    return encodeWav(downsample(merged, sr, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE)
  }

  /** 中止录音，丢弃数据 */
  function abort() {
    isRecording.value = false
    chunks = []
    mic.stop()
  }

  onUnmounted(() => abort())

  return {
    isSupported: mic.isSupported,
    isRecording,
    errorMsg: mic.errorMsg,
    start,
    stop,
    abort,
  }
}
