<template>
  <div class="chat-input-wrapper">
    <!-- 录音浮层 -->
    <transition name="voice-fade">
      <div v-if="pressing" class="voice-mask">
        <div class="voice-card" :class="{ canceling }">
          <div class="voice-wave">
            <span class="bar"></span>
            <span class="bar"></span>
            <span class="bar"></span>
            <span class="bar"></span>
            <span class="bar"></span>
          </div>
          <div class="voice-text">
            <template v-if="speech.finalText.value || speech.interimText.value">
              {{ speech.finalText.value }}<span class="interim">{{ speech.interimText.value }}</span>
            </template>
            <template v-else>
              <span class="placeholder">正在聆听...</span>
            </template>
          </div>
          <div class="voice-tip">
            <template v-if="canceling">
              <span class="cancel-hint">松开手指 取消发送</span>
            </template>
            <template v-else>
              松开发送 / <span class="up-hint">上滑取消</span>
            </template>
          </div>
        </div>
      </div>
    </transition>

    <div class="input-box" :class="{ 'voice-mode': voiceMode }">
      <!-- 模式切换：键盘 ↔ 麦克风 -->
      <el-tooltip :content="voiceMode ? '切换为键盘输入' : '切换为语音输入'" placement="top">
        <el-button
          size="small"
          circle
          class="action-btn mode-btn"
          :disabled="chatStore.loading"
          @click="toggleVoiceMode"
        >
          <el-icon :size="14">
            <EditPen v-if="voiceMode" />
            <Microphone v-else />
          </el-icon>
        </el-button>
      </el-tooltip>

      <!-- 文本模式：输入框 -->
      <el-input
        v-if="!voiceMode"
        v-model="inputText"
        placeholder="输入产品名称或询价需求..."
        :disabled="chatStore.loading"
        class="chat-input"
        @keyup.enter="handleSend"
      />

      <!-- 语音模式：按住说话条 -->
      <div
        v-else
        class="voice-bar"
        :class="{ pressing: pressing, canceling: canceling }"
        @pointerdown="onMicPointerDown"
        @pointermove="onMicPointerMove"
        @pointerup="onMicPointerUp"
        @pointercancel="onMicPointerCancel"
        @contextmenu.prevent
      >
        <span v-if="!pressing">按住 说话</span>
        <span v-else-if="canceling">松开 取消</span>
        <span v-else>松开 发送</span>
      </div>

      <el-tooltip :content="chatStore.enableWebSearch ? '联网搜索已开启' : '开启联网搜索'" placement="top">
        <el-button
          :type="chatStore.enableWebSearch ? 'primary' : 'default'"
          size="small"
          circle
          class="action-btn"
          @click="chatStore.setEnableWebSearch(!chatStore.enableWebSearch)"
        >
          <el-icon :size="14"><Connection /></el-icon>
        </el-button>
      </el-tooltip>

      <el-tooltip :content="chatStore.enableThinking ? '深度思考已开启' : '开启深度思考'" placement="top">
        <el-button
          :type="chatStore.enableThinking ? 'warning' : 'default'"
          size="small"
          circle
          class="action-btn"
          @click="chatStore.setEnableThinking(!chatStore.enableThinking)"
        >
          <el-icon :size="14"><MagicStick /></el-icon>
        </el-button>
      </el-tooltip>

      <!-- 发送/停止按钮（语音模式下隐藏发送，松开自动发） -->
      <el-tooltip
        v-if="!voiceMode || chatStore.loading"
        :content="chatStore.loading ? '停止生成' : '发送'"
        placement="top"
      >
        <el-button
          :type="chatStore.loading ? 'danger' : 'primary'"
          circle
          class="send-btn"
          :disabled="!chatStore.loading && !inputText.trim()"
          @click="chatStore.loading ? handleStop() : handleSend()"
        >
          <el-icon :size="14">
            <VideoPause v-if="chatStore.loading" />
            <Promotion v-else />
          </el-icon>
        </el-button>
      </el-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, toRefs } from "vue"
import { Connection, Promotion, MagicStick, VideoPause, Microphone, EditPen } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { useChatStore } from "../../stores/chat"
import { sendMessageStream } from "../../api/chat"
import { uuid } from "../../utils/uuid"
import { useSpeechRecognition } from "../../composables/useSpeechRecognition"
import type { ChatMessage } from "../../types/message"

const chatStore = useChatStore()
const inputText = ref("")
let abortController: AbortController | null = null

// ===== 输入模式：'text' 文本 / 'voice' 语音 =====
const voiceMode = ref(false)

// ===== 语音输入（按住说话，松开发送） =====
const speechApi = useSpeechRecognition()
const speech = toRefs(speechApi)

const pressing = ref(false)       // 是否正在按住说话
const canceling = ref(false)      // 上滑超阈值，松手将取消

const CANCEL_THRESHOLD = 60       // 上滑多少 px 视为取消
const MIN_PRESS_MS = 400          // 按住时长不足判定为误触

let pressStartY = 0
let pressStartTime = 0
let textBackup = ""

function toggleVoiceMode() {
  if (chatStore.loading) return
  if (!voiceMode.value && !speechApi.isSupported.value) {
    ElMessage.warning("当前浏览器不支持语音识别，建议使用 Edge 或 Chrome")
    return
  }
  voiceMode.value = !voiceMode.value
}

// 录音中实时把识别结果写到输入框
watch(
  () => speechApi.finalText.value + speechApi.interimText.value,
  (composed) => {
    if (pressing.value) {
      inputText.value = composed
    }
  }
)

watch(speechApi.errorMsg, (msg) => {
  if (msg) ElMessage.warning(msg)
})

function onMicPointerDown(e: PointerEvent) {
  if (chatStore.loading) return
  if (!speechApi.isSupported.value) {
    ElMessage.warning("当前浏览器不支持语音识别，建议使用 Edge 或 Chrome")
    return
  }
  // 鼠标右键忽略
  if (e.button !== undefined && e.button !== 0) return

  // 把后续 move/up 事件都锁定到按钮，免得手指移出按钮就丢事件
  ;(e.currentTarget as HTMLElement)?.setPointerCapture?.(e.pointerId)

  textBackup = inputText.value
  inputText.value = ""
  pressStartY = e.clientY
  pressStartTime = Date.now()
  pressing.value = true
  canceling.value = false
  speechApi.start()
}

function onMicPointerMove(e: PointerEvent) {
  if (!pressing.value) return
  const dy = pressStartY - e.clientY
  canceling.value = dy > CANCEL_THRESHOLD
}

async function onMicPointerUp(e: PointerEvent) {
  if (!pressing.value) return
  ;(e.currentTarget as HTMLElement)?.releasePointerCapture?.(e.pointerId)

  const wasCanceling = canceling.value
  const pressDuration = Date.now() - pressStartTime

  pressing.value = false
  canceling.value = false

  if (wasCanceling) {
    speechApi.abort()
    inputText.value = textBackup
    return
  }

  if (pressDuration < MIN_PRESS_MS) {
    speechApi.abort()
    inputText.value = textBackup
    ElMessage.info("按住按钮说话")
    return
  }

  // 正常松开：停止识别 → 等最终 transcript → 自动发送
  speechApi.stop()
  // 给浏览器 ~400ms 把最后一段 interim 转成 final 并触发 onresult
  await new Promise((r) => setTimeout(r, 400))

  const finalText = (speechApi.finalText.value || speechApi.interimText.value).trim()
  if (!finalText) {
    inputText.value = textBackup
    ElMessage.info("没有识别到语音")
    return
  }

  inputText.value = textBackup
    ? `${textBackup} ${finalText}`
    : finalText
  handleSend()
}

function onMicPointerCancel() {
  if (!pressing.value) return
  pressing.value = false
  canceling.value = false
  speechApi.abort()
  inputText.value = textBackup
}

const TOOL_NAMES: Record<string, string> = {
  search_products: "搜索商品",
  get_latest_prices: "查询最新价格",
  get_price_history: "查询价格趋势",
  get_price_ranking: "查询涨跌排行",
  web_search: "搜索互联网",
  "分析问题": "分析问题并查询数据",
}

function handleStop() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  const convId = chatStore.conversationId
  chatStore.setLoading(false, convId)
  chatStore.setStreaming(false, convId)
  chatStore.setToolStatus("", convId)
  // 给当前消息加上耗时
  const msgs = chatStore.messages
  const lastMsg = msgs[msgs.length - 1]
  if (lastMsg && lastMsg.role === "assistant" && !lastMsg.duration) {
    chatStore.updateLastMessage({
      duration: Date.now() - lastMsg.timestamp,
    }, convId)
  }
}

async function handleSend() {
  // 发送前若还在录音，先停掉，确保最后一段 interim 也变成 final
  if (speechApi.isRecording.value) {
    speechApi.stop()
    // 给浏览器一点时间把最终 transcript 触发出来
    await new Promise((r) => setTimeout(r, 100))
  }

  const text = inputText.value.trim()
  if (!text || chatStore.loading) return

  // 如果没有 conversationId，先生成一个
  if (!chatStore.conversationId) {
    chatStore.setConversationId(uuid())
  }

  // 捕获当前对话 ID，后续所有操作都绑定到这个 ID
  const targetConvId = chatStore.conversationId

  const userMsg: ChatMessage = {
    id: Date.now().toString(),
    role: "user",
    content: text,
    suggestions: [],
    timestamp: Date.now(),
  }
  chatStore.addMessage(userMsg, targetConvId)
  chatStore.persistMessage(userMsg, targetConvId)
  inputText.value = ""
  chatStore.setLoading(true, targetConvId)
  chatStore.setStreaming(true, targetConvId)
  chatStore.setToolStatus("", targetConvId)

  const startTime = Date.now()
  abortController = new AbortController()

  const aiMsg: ChatMessage = {
    id: (Date.now() + 1).toString(),
    role: "assistant",
    content: "",
    thinking: "",
    suggestions: [],
    timestamp: Date.now(),
  }
  chatStore.addMessage(aiMsg, targetConvId)

  try {
    await sendMessageStream(
      text,
      targetConvId,
      chatStore.enableThinking,
      chatStore.enableWebSearch,
      {
        onToken(token: string) {
          chatStore.setToolStatus("", targetConvId)
          chatStore.appendToLastMessage(token, targetConvId)
        },
        onThinkingToken(token: string) {
          chatStore.setToolStatus("", targetConvId)
          chatStore.appendThinkingToLastMessage(token, targetConvId)
        },
        onToolStart(toolName: string) {
          const displayName = TOOL_NAMES[toolName] || toolName
          chatStore.setToolStatus(`正在${displayName}...`, targetConvId)
          chatStore.addToolCall(toolName, displayName, targetConvId)
        },
        onToolEnd(toolName: string) {
          chatStore.completeToolCall(toolName, targetConvId)
          chatStore.setToolStatus("正在整理结果...", targetConvId)
        },
        onDone(data) {
          chatStore.updateLastMessage({
            suggestions: data.suggestions || [],
            duration: Date.now() - startTime,
            prompt_tokens: data.usage?.prompt_tokens || 0,
            completion_tokens: data.usage?.completion_tokens || 0,
            total_tokens: data.usage?.total_tokens || 0,
          }, targetConvId)
          chatStore.setToolStatus("", targetConvId)
          // 保存 AI 回复到后端
          const state = chatStore.messages
          const lastMsg = state[state.length - 1]
          if (lastMsg && lastMsg.role === "assistant") {
            chatStore.persistMessage(lastMsg, targetConvId)
          }
          chatStore.loadConversations()
        },
        onError(error: string) {
          chatStore.updateLastMessage({
            content: `抱歉，请求出错了：${error}`,
          }, targetConvId)
          chatStore.setToolStatus("", targetConvId)
        },
      },
      abortController.signal
    )
  } catch (e: any) {
    if (e.name !== "AbortError") {
      chatStore.updateLastMessage({
        content: "抱歉，请求出错了，请稍后再试。",
      }, targetConvId)
    }
  } finally {
    abortController = null
    chatStore.setLoading(false, targetConvId)
    chatStore.setStreaming(false, targetConvId)
    chatStore.setToolStatus("", targetConvId)
  }
}

function sendFromOutside(text: string) {
  inputText.value = text
  handleSend()
}

defineExpose({ sendFromOutside })
</script>

<style scoped>
.chat-input-wrapper {
  max-width: 800px;
  margin: 0 auto;
}

.input-box {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #e4e7ed;
  border-radius: 20px;
  padding: 4px 4px 4px 12px;
  background: #fff;
  transition: border-color 0.25s, box-shadow 0.25s;
}

.input-box:focus-within {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
}

.action-btn {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.mode-btn {
  margin-right: 2px;
}

/* 语音模式：按住说话条 */
.voice-bar {
  flex: 1;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 16px;
  font-size: 13px;
  color: #606266;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.voice-bar:hover {
  background: #ecf5ff;
}

.voice-bar.pressing {
  background: #ecf5ff;
  color: #409eff;
}

.voice-bar.canceling {
  background: #fef0f0;
  color: #f56c6c;
}

.input-box.voice-mode {
  padding: 6px 4px 6px 6px;
}

/* ===== 录音浮层 ===== */
.voice-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.32);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  pointer-events: none; /* 不拦截事件，让 pointermove/up 继续打到按钮上 */
}

.voice-card {
  width: min(320px, 80vw);
  background: #fff;
  border-radius: 16px;
  padding: 24px 22px 20px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  text-align: center;
  transition: background-color 0.2s, color 0.2s;
}

.voice-card.canceling {
  background: #fef0f0;
}

.voice-wave {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  gap: 4px;
  height: 36px;
  margin-bottom: 16px;
}

.voice-wave .bar {
  width: 4px;
  background: linear-gradient(to top, #409eff, #6366f1);
  border-radius: 2px;
  animation: wave 1.1s ease-in-out infinite;
}

.voice-wave .bar:nth-child(1) { animation-delay: 0s;     height: 16px; }
.voice-wave .bar:nth-child(2) { animation-delay: 0.15s;  height: 24px; }
.voice-wave .bar:nth-child(3) { animation-delay: 0.3s;   height: 32px; }
.voice-wave .bar:nth-child(4) { animation-delay: 0.15s;  height: 24px; }
.voice-wave .bar:nth-child(5) { animation-delay: 0s;     height: 16px; }

.voice-card.canceling .voice-wave .bar {
  background: linear-gradient(to top, #f56c6c, #f78989);
}

@keyframes wave {
  0%, 100% { transform: scaleY(0.4); }
  50%      { transform: scaleY(1);   }
}

.voice-text {
  min-height: 48px;
  max-height: 100px;
  overflow-y: auto;
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  word-break: break-word;
  margin-bottom: 12px;
}

.voice-text .interim {
  color: #909399;
}

.voice-text .placeholder {
  color: #c0c4cc;
}

.voice-tip {
  font-size: 12px;
  color: #909399;
}

.up-hint {
  color: #409eff;
}

.cancel-hint {
  color: #f56c6c;
  font-weight: 500;
}

.voice-fade-enter-active,
.voice-fade-leave-active {
  transition: opacity 0.2s ease;
}

.voice-fade-enter-from,
.voice-fade-leave-to {
  opacity: 0;
}

.chat-input {
  flex: 1;
}

.chat-input :deep(.el-input__wrapper) {
  box-shadow: none;
  padding: 0;
  background: transparent;
}

.chat-input :deep(.el-input__wrapper:hover) {
  box-shadow: none;
}

.chat-input :deep(.el-input__wrapper:focus-within) {
  box-shadow: none;
}

.chat-input :deep(.el-input__inner) {
  font-size: 14px;
}

.send-btn {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
}
</style>
