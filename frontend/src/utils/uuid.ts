/**
 * 生成 UUID v4。
 * 优先用浏览器原生 crypto.randomUUID（HTTPS / localhost 才有），
 * 退化使用 crypto.getRandomValues（HTTP 也能用），
 * 最后兜底 Math.random（极端环境）。
 */
export function uuid(): string {
  // 现代浏览器 + HTTPS / localhost
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID()
  }

  // HTTP 下也可用：手动用 16 字节随机数拼出 RFC4122 v4
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40 // version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80 // variant 10
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  // 极端兜底（伪随机，不推荐生产）
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === "x" ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}
