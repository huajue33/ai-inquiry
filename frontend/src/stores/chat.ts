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
import { getModels, type ModelOption } from "../api/chat"

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

  // 模型选择
  const availableModels = ref<ModelOption[]>([])
  const defaultModel = ref<string>("")
  const selectedModel = ref<string>(localStorage.getItem("selected_model") || "")

  // 当前选中模型是否支持深度思考
  const currentModelSupportsThinking = computed(() => {
    const m = availableModels.value.find((x) => x.id === selectedModel.value)
    // 列表未加载时默认允许，避免初始误禁用
    return m ? m.supports_thinking : true
  })

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

  // 加载可选模型列表
  async function loadModels() {
    try {
      const res = await getModels()
      availableModels.value = res.models
      defaultModel.value = res.default
      // 已选模型不在列表中（或未选过）→ 回退默认
      const valid = res.models.some((m) => m.id === selectedModel.value)
      if (!valid) {
        selectedModel.value = res.default
        localStorage.setItem("selected_model", res.default)
      }
      // 当前模型不支持思考时，强制关闭深度思考开关
      if (!currentModelSupportsThinking.value) {
        enableThinking.value = false
      }
    } catch {
      // ignore
    }
  }

  // 切换模型
  function setModel(id: string) {
    selectedModel.value = id
    localStorage.setItem("selected_model", id)
    // 新模型不支持思考时，关闭深度思考
    if (!currentModelSupportsThinking.value) {
      enableThinking.value = false
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
  /** 向指定对话添加一条消息 */
  function addMessage(msg: ChatMessage, convId?: string) {
    getState(convId).messages.push(msg)
  }

  /** 更新当前对话最后一条助手消息的部分字段 */
  function updateLastMessage(updates: Partial<ChatMessage>, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant") {
      Object.assign(last, updates)
    }
  }

  /** 向最后一条助手消息追加回复内容token */
  function appendToLastMessage(token: string, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant") {
      last.content += token
    }
  }

  /** 向最后一条助手消息追加思考过程token */
  function appendThinkingToLastMessage(token: string, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant") {
      if (!last.thinking) last.thinking = ""
      last.thinking += token
    }
  }

  /** 记录工具调用开始，在消息中创建running状态的toolCall */
  function addToolCall(name: string, displayName: string, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant") {
      if (!last.toolCalls) last.toolCalls = []
      last.toolCalls.push({ name, displayName, status: "running" })
    }
  }

  /** 标记指定工具调用为完成状态 */
  function completeToolCall(name: string, convId?: string) {
    const state = getState(convId)
    const last = state.messages[state.messages.length - 1]
    if (last && last.role === "assistant" && last.toolCalls) {
      const tool = [...last.toolCalls].reverse().find(t => t.name === name && t.status === "running")
      if (tool) tool.status = "done"
    }
  }

  /** 设置指定对话的加载状态 */
  function setLoading(val: boolean, convId?: string) {
    getState(convId).loading = val
  }

  /** 设置指定对话的流式输出状态 */
  function setStreaming(val: boolean, convId?: string) {
    getState(convId).streaming = val
  }

  /** 设置指定对话的工具调用状态文本 */
  function setToolStatus(status: string, convId?: string) {
    getState(convId).toolStatus = status
  }

  /** 设置全局思考模式开关（模型不支持思考时忽略开启请求） */
  function setEnableThinking(val: boolean) {
    if (val && !currentModelSupportsThinking.value) return
    enableThinking.value = val
  }

  /** 设置全局联网搜索开关 */
  function setEnableWebSearch(val: boolean) {
    enableWebSearch.value = val
  }

  /** 设置当前活跃的对话ID */
  function setConversationId(id: string) {
    conversationId.value = id
  }

  // 检查某个对话是否正在加载
  function isConversationLoading(id: string): boolean {
    return conversationStates.has(id) && conversationStates.get(id)!.loading
  }

  /** 重置全部会话相关状态（用于退出登录 / 切换账号，避免串号） */
  function reset() {
    conversationId.value = ""
    conversations.value = []
    conversationStates.clear()
    enableThinking.value = false
    enableWebSearch.value = false
    availableModels.value = []
    defaultModel.value = ""
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
    availableModels,
    defaultModel,
    selectedModel,
    currentModelSupportsThinking,
    addMessage,
    updateLastMessage,
    appendToLastMessage,
    appendThinkingToLastMessage,
    addToolCall,
    completeToolCall,
    persistMessage,
    loadConversations,
    loadModels,
    setModel,
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
    reset,
  }
})
