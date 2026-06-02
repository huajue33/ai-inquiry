/**
 * 流式发送消息（SSE），支持思考模式、联网搜索和中断
 */
export async function sendMessageStream(
  message: string,
  conversationId: string | undefined,
  enableThinking: boolean,
  enableWebSearch: boolean,
  callbacks: {
    onToken: (token: string) => void
    onThinkingToken?: (token: string) => void
    onToolStart?: (toolName: string) => void
    onToolEnd?: (toolName: string) => void
    onDone: (data: { suggestions: string[]; conversation_id: string; usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number } }) => void
    onError: (error: string) => void
  },
  abortSignal?: AbortSignal
): Promise<void> {
  let token = localStorage.getItem("token")

  const doFetch = async (authToken: string | null) => {
    return fetch("/api/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        enable_thinking: enableThinking,
        enable_web_search: enableWebSearch,
      }),
      signal: abortSignal,
    })
  }

  let response = await doFetch(token)

  // 如果 401，尝试用 refresh token 续期后重试
  if (response.status === 401) {
    const refreshTokenStr = localStorage.getItem("refresh_token")
    if (refreshTokenStr) {
      try {
        const refreshRes = await fetch("/api/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshTokenStr }),
        })
        if (refreshRes.ok) {
          const data = await refreshRes.json()
          localStorage.setItem("token", data.access_token)
          localStorage.setItem("refresh_token", data.refresh_token)
          token = data.access_token
          response = await doFetch(token)
        } else {
          localStorage.removeItem("token")
          localStorage.removeItem("refresh_token")
          localStorage.removeItem("user")
          window.location.href = "/login"
          return
        }
      } catch {
        localStorage.removeItem("token")
        localStorage.removeItem("refresh_token")
        localStorage.removeItem("user")
        window.location.href = "/login"
        return
      }
    } else {
      localStorage.removeItem("token")
      localStorage.removeItem("user")
      window.location.href = "/login"
      return
    }
  }

  if (!response.ok) {
    callbacks.onError(`请求失败: ${response.status}`)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    callbacks.onError("无法读取响应流")
    return
  }

  const decoder = new TextDecoder()
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split("\n")
      buffer = lines.pop() || ""

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith("data: ")) continue

        const jsonStr = trimmed.slice(6)
        try {
          const event = JSON.parse(jsonStr)

          switch (event.event) {
            case "token":
              callbacks.onToken(event.data)
              break
            case "thinking_token":
              callbacks.onThinkingToken?.(event.data)
              break
            case "tool_start":
              callbacks.onToolStart?.(event.data)
              break
            case "tool_end":
              callbacks.onToolEnd?.(event.data)
              break
            case "done":
              callbacks.onDone(event.data)
              break
            case "error":
              callbacks.onError(event.data)
              break
          }
        } catch {
          // 忽略解析错误
        }
      }
    }
  } catch (e: any) {
    if (e.name === "AbortError") {
      // 用户主动中断，不报错
      return
    }
    throw e
  } finally {
    reader.releaseLock()
  }
}
