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

/** 获取当前用户的对话列表 */
export function getConversations(): Promise<{ conversations: ConversationItem[] }> {
  return request.get("/conversations/")
}

/** 创建新的对话 */
export function createConversation(): Promise<{ id: string; title: string }> {
  return request.post("/conversations/create")
}

/** 获取指定对话的详情及历史消息 */
export function getConversation(id: string): Promise<{ id: string; title: string; messages: MessageItem[] }> {
  return request.get(`/conversations/${id}`)
}

/** 更新对话标题 */
export function updateConversationTitle(id: string, title: string): Promise<any> {
  return request.put(`/conversations/${id}/title`, { title })
}

/** 删除指定对话 */
export function deleteConversation(id: string): Promise<any> {
  return request.delete(`/conversations/${id}`)
}

/** 回滚对话：把指定消息（含）及其之后的消息标记为已回滚（软删除） */
export function rollbackConversation(id: string, messageId: number): Promise<{ ok: boolean; rolled_back: number }> {
  return request.post(`/conversations/${id}/rollback`, { message_id: messageId })
}

/** 将消息保存到指定对话中 */
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
