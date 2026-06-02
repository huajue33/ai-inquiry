import { defineStore } from "pinia"
import { ref, reactive, computed } from "vue"
import type { ChatMessage } from "../types/message"
import {
  getConversations,
  getConversation,
  deleteConversation,
  saveMessage,
  type ConversationItem,
} from "../api/conversation"

/**
 * 每个对话的独立状态
 */
interface ConversationState {
  messages: ChatMessage[]
  loading: boolean
  streaming: boolean
  toolStatus: string
}

export const useChatStore = defineStore("chat", () => {
  // 当前活跃的对话 ID
  const conversationId = ref<string>("")
  // 对话列表
  const conversations = ref<ConversationItem[]>([])
  // 全局设置
  const enableThinking = ref(false)
  const enableWebSearch = ref(false)

  // 每个对话的独立状态 Map
  const conversationStates = reactive<Map<string, ConversationState>>(new Map())

  // 获取当前对话的状态
  function getState(convId?: string): ConversationState {
    const id = convId || conversationId.value
    if (!id) {
      return { messages: [], loading: false, streaming: false, toolStatus: "" }
    }
    if (!conversationStates.has(id)) {
      conversationStates.set(id, {
        messages: [],
        loading: false,
        streaming: false,
        toolStatus: "",
      })
    }
    return conversationStates.get(id)!
  }

  // 当前对话的响应式计算属性
  const messages = computed(() => getState().messages)
  const loading = computed(() => getState().loading)
  const streaming = computed(() => getState().streaming)
  const toolStatus = computed(() => getState().toolStatus)

  // 加载对话列表
  async function loadConversations() {
    try {
      const res = await getConversations()
      conversations.value = res.conversations
    } catch {
      // ignore
    }
  }

  // 新建对话
  async function newConversation() {
    conversationId.value = ""
    await loadConversations()
  }

  // 切换到某个对话（不中断其他对话的流）
  async function switchConversation(id: string) {
    if (id === conversationId.value) return

    conversationId.value = id

    // 如果该对话已有本地状态（正在运行中），直接显示
    if (conversationStates.has(id) && getState(id).messages.length > 0) {
      return
    }

    // 否则从后端加载
    try {
      const res = await getConversation(id)
      const state = getState(id)
      state.messages = res.messages.map((msg) => ({
        id: msg.id.toString(),
        role: msg.role as "user" | "assistant",
        content: msg.content,
        thinking: msg.thinking || undefined,
        suggestions: msg.suggestions || [],
        duration: msg.duration || undefined,
        timestamp: new Date(msg.created_at).getTime(),
      }))
    } catch {
      // ignore
    }
  }

  // 删除对话
  async function removeConversation(id: string) {
    try {
      await deleteConversation(id)
      conversations.value = conversations.value.filter(c => c.id !== id)
      conversationStates.delete(id)
      if (conversationId.value === id) {
        conversationId.value = ""
      }
    } catch {
      // ignore
    }
  }

  // 保存消息到后端
  async function persistMessage(msg: ChatMessage, convId?: string) {
    const id = convId || conversationId.value
    if (!id) return
    try {
      await saveMessage({
        conversation_id: id,
        role: msg.role,
        content: msg.content,
        thinking: msg.thinking,
        suggestions: msg.suggestions,
        duration: msg.duration,
        prompt_tokens: msg.prompt_tokens || 0,
        completion_tokens: msg.completion_tokens || 0,
        total_tokens: msg.total_tokens || 0,
      })
    } catch {
      // ignore
    }
  }

  // 以下操作都针对指定的对话（默认当前对话）
  function addMessage(msg: ChatMessage, convId?: string) {
    getState(convId).messages.push(msg)
  }

  function updateLastMessage(updates: Partial<ChatMessage>, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant") {
      Object.assign(last, updates)
    }
  }

  function appendToLastMessage(token: string, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant") {
      last.content += token
    }
  }

  function appendThinkingToLastMessage(token: string, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant") {
      if (!last.thinking) last.thinking = ""
      last.thinking += token
    }
  }

  function addToolCall(name: string, displayName: string, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant") {
      if (!last.toolCalls) last.toolCalls = []
      last.toolCalls.push({ name, displayName, status: "running" })
    }
  }

  function completeToolCall(name: string, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant" && last.toolCalls) {
      const tool = [...last.toolCalls].reverse().find(t => t.name === name && t.status === "running")
      if (tool) tool.status = "done"
    }
  }

  function setLoading(val: boolean, convId?: string) {
    getState(convId).loading = val
  }

  function setStreaming(val: boolean, convId?: string) {
    getState(convId).streaming = val
  }

  function setToolStatus(status: string, convId?: string) {
    getState(convId).toolStatus = status
  }

  function setEnableThinking(val: boolean) {
    enableThinking.value = val
  }

  function setEnableWebSearch(val: boolean) {
    enableWebSearch.value = val
  }

  function setConversationId(id: string) {
    conversationId.value = id
  }

  // 检查某个对话是否正在加载
  function isConversationLoading(id: string): boolean {
    return conversationStates.has(id) && conversationStates.get(id)!.loading
  }

  return {
    messages,
    conversationId,
    conversations,
    loading,
    streaming,
    toolStatus,
    enableThinking,
    enableWebSearch,
    addMessage,
    updateLastMessage,
    appendToLastMessage,
    appendThinkingToLastMessage,
    addToolCall,
    completeToolCall,
    persistMessage,
    loadConversations,
    newConversation,
    switchConversation,
    removeConversation,
    isConversationLoading,
    setLoading,
    setStreaming,
    setToolStatus,
    setEnableThinking,
    setEnableWebSearch,
    setConversationId,
  }
})
