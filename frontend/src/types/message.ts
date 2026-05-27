export interface ToolCall {
  name: string
  displayName: string
  status: "running" | "done"
}

export interface ChatMessage {
  id: string
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
