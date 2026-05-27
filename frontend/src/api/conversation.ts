import request from "./request"

export interface ConversationItem {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface MessageItem {
  id: number
  role: string
  content: string
  thinking?: string
  suggestions: string[]
  duration?: number
  created_at: string
}

export function getConversations(): Promise<{ conversations: ConversationItem[] }> {
  return request.get("/conversations/")
}

export function createConversation(): Promise<{ id: string; title: string }> {
  return request.post("/conversations/create")
}

export function getConversation(id: string): Promise<{ id: string; title: string; messages: MessageItem[] }> {
  return request.get(`/conversations/${id}`)
}

export function updateConversationTitle(id: string, title: string): Promise<any> {
  return request.put(`/conversations/${id}/title`, { title })
}

export function deleteConversation(id: string): Promise<any> {
  return request.delete(`/conversations/${id}`)
}

export function saveMessage(data: {
  conversation_id: string
  role: string
  content: string
  thinking?: string
  suggestions?: string[]
  duration?: number
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}): Promise<{ id: number }> {
  return request.post("/conversations/message", data)
}
