import axios from "axios"

const request = axios.create({
  baseURL: "/api",
  timeout: 120000,
})

// 是否正在刷新 token
let isRefreshing = false
// 等待刷新完成的请求队列
let refreshSubscribers: Array<(token: string) => void> = []

function subscribeTokenRefresh(cb: (token: string) => void) {
  refreshSubscribers.push(cb)
}

function onTokenRefreshed(newToken: string) {
  refreshSubscribers.forEach((cb) => cb(newToken))
  refreshSubscribers = []
}

async function refreshToken(): Promise<string | null> {
  const refreshTokenStr = localStorage.getItem("refresh_token")
  if (!refreshTokenStr) return null

  try {
    const res = await axios.post("/api/auth/refresh", {
      refresh_token: refreshTokenStr,
    })
    const { access_token, refresh_token } = res.data
    localStorage.setItem("token", access_token)
    localStorage.setItem("refresh_token", refresh_token)
    return access_token
  } catch {
    // refresh token 也过期了，清除登录状态
    localStorage.removeItem("token")
    localStorage.removeItem("refresh_token")
    localStorage.removeItem("user")
    return null
  }
}

request.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const originalRequest = error.config

    // 401 且不是 refresh 请求本身 且没有重试过
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes("/auth/refresh") &&
      !originalRequest.url?.includes("/auth/login")
    ) {
      originalRequest._retry = true

      if (!isRefreshing) {
        isRefreshing = true
        const newToken = await refreshToken()
        isRefreshing = false

        if (newToken) {
          onTokenRefreshed(newToken)
          // 用新 token 重试原请求
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return request(originalRequest)
        } else {
          // 刷新失败，跳转登录
          refreshSubscribers = []
          window.location.href = "/login"
          return Promise.reject(error)
        }
      } else {
        // 正在刷新中，排队等待
        return new Promise((resolve) => {
          subscribeTokenRefresh((newToken: string) => {
            originalRequest.headers.Authorization = `Bearer ${newToken}`
            resolve(request(originalRequest))
          })
        })
      }
    }

    // 其他 401（如 refresh 失败）
    if (error.response?.status === 401) {
      localStorage.removeItem("token")
      localStorage.removeItem("refresh_token")
      localStorage.removeItem("user")
      window.location.href = "/login"
    }

    return Promise.reject(error)
  }
)

export default request
