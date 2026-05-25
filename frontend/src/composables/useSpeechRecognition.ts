import { ref, onUnmounted } from "vue"

/**
 * 浏览器原生 Web Speech API 封装
 *
 * - Edge / Chrome：支持（Chrome 国内版需要可访问 Google 服务）
 * - Safari：部分支持
 * - Firefox：不支持
 *
 * 工作原理：用户说话 → 浏览器送到云端识别 → 返回 transcript
 */
export function useSpeechRecognition() {
  const isSupported = ref(
    typeof window !== "undefined" &&
      ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
  )

  const isRecording = ref(false)
  // 已确认的最终文本（多次说话累加）
  const finalText = ref("")
  // 当前正在识别的临时文本
  const interimText = ref("")
  const errorMsg = ref("")

  let recognition: any = null

  function start() {
    if (!isSupported.value) {
      errorMsg.value = "当前浏览器不支持语音识别，建议使用 Edge 或 Chrome"
      return false
    }
    if (isRecording.value) return false

    const SR =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    recognition = new SR()
    recognition.lang = "zh-CN"
    recognition.continuous = true        // 允许说较长内容
    recognition.interimResults = true    // 流式中间结果
    recognition.maxAlternatives = 1

    finalText.value = ""
    interimText.value = ""
    errorMsg.value = ""

    recognition.onresult = (event: any) => {
      let interim = ""
      let final = ""
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          final += result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      if (final) finalText.value += final
      interimText.value = interim
    }

    recognition.onerror = (event: any) => {
      const code = event.error || "unknown"
      const map: Record<string, string> = {
        "no-speech": "没有检测到语音",
        "audio-capture": "无法访问麦克风",
        "not-allowed": "请允许浏览器使用麦克风",
        "network": "网络错误，可能是无法访问语音识别服务",
        "aborted": "",
      }
      errorMsg.value = map[code] ?? `语音识别失败：${code}`
      isRecording.value = false
    }

    recognition.onend = () => {
      isRecording.value = false
    }

    try {
      recognition.start()
      isRecording.value = true
      return true
    } catch (e) {
      errorMsg.value = "启动语音识别失败"
      isRecording.value = false
      return false
    }
  }

  function stop() {
    if (recognition && isRecording.value) {
      try {
        recognition.stop()
      } catch {
        /* ignore */
      }
    }
    isRecording.value = false
  }

  function abort() {
    if (recognition) {
      try {
        recognition.abort()
      } catch {
        /* ignore */
      }
    }
    isRecording.value = false
  }

  onUnmounted(() => abort())

  return {
    isSupported,
    isRecording,
    finalText,
    interimText,
    errorMsg,
    start,
    stop,
    abort,
  }
}
