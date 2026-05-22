export type CardType =
  | "price_card"
  | "price_list"
  | "trend_chart"
  | "compare_table"
  | "ranking_list"
  | "alert_card"
  | "clarify_card"

export interface CardData {
  type: CardType
  data: Record<string, any>
}

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
  cards: CardData[]
  suggestions: string[]
  timestamp: number
  duration?: number
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

export interface ChatResponse {
  reply: string
  cards: CardData[]
  suggestions: string[]
  conversation_id: string
}
