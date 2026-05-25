<template>
  <div class="chat-input-wrapper">
    <div class="input-box">
      <el-input
        v-model="inputText"
        placeholder="输入产品名称或询价需求..."
        :disabled="chatStore.loading"
        class="chat-input"
        @keyup.enter="handleSend"
      />
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
      <!-- 发送/停止按钮 -->
      <el-tooltip :content="chatStore.loading ? '停止生成' : '发送'" placement="top">
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
import { ref } from "vue"
import { Promotion, MagicStick, VideoPause } from "@element-plus/icons-vue"
import { useChatStore } from "../../stores/chat"
import { sendMessageStream } from "../../api/chat"
import type { ChatMessage } from "../../types/card"

const chatStore = useChatStore()
const inputText = ref("")
let abortController: AbortController | null = null

const TOOL_NAMES: Record<string, string> = {
  query_latest_price: "查询最新价格",
  query_price_trend: "查询价格趋势",
  query_price_ranking: "查询涨跌排行",
  compare_products: "对比产品价格",
  clarify_product: "分析产品分类",
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
  const text = inputText.value.trim()
  if (!text || chatStore.loading) return

  // 如果没有 conversationId，先生成一个
  if (!chatStore.conversationId) {
    chatStore.setConversationId(crypto.randomUUID())
  }

  // 捕获当前对话 ID，后续所有操作都绑定到这个 ID
  const targetConvId = chatStore.conversationId

  const userMsg: ChatMessage = {
    id: Date.now().toString(),
    role: "user",
    content: text,
    cards: [],
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
    cards: [],
    suggestions: [],
    timestamp: Date.now(),
  }
  chatStore.addMessage(aiMsg, targetConvId)

  try {
    await sendMessageStream(
      text,
      targetConvId,
      chatStore.enableThinking,
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
            cards: data.cards || [],
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
