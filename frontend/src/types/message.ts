export interface ToolCall {
  name: string
  displayName: string
  status: "running" | "done"
}

export interface ChatMessage {
  id: string
  /** 后端持久化后的真实数据库 id（用于回滚定位；与 id 分开，避免改动 :key） */
  dbId?: number
  role: "user" | "assistant"
  content: string
  thinking?: string
  toolCalls?: ToolCall[]
  suggestions: string[]
  timestamp: number
  duration?: number
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}
