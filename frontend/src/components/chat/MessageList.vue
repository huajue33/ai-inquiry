<template>
  <div class="message-list" ref="listRef">
    <div v-if="chatStore.messages.length === 0" class="welcome">
      <div class="welcome-icon">
        <img src="/favicon.svg" alt="AI" class="welcome-logo" />
      </div>
      <h2>您好，我是您的 AI 采销询价助手</h2>
      <p class="welcome-desc">基于实时价格数据库，助您快速查价、分析趋势、对比品牌。</p>

      <div class="feature-cards">
        <div class="feature-card" @click="$emit('quick', '今日蔬菜涨价排行')">
          <div class="feature-card-header">
            <el-icon :size="20" class="feature-icon price"><TrendCharts /></el-icon>
            <span class="feature-title">价格趋势分析</span>
          </div>
          <p class="feature-desc">查看产品涨跌排行，掌握市场动态</p>
          <div class="feature-examples">
            <span class="feature-example" @click.stop="$emit('quick', '今日蔬菜涨价排行')">今日蔬菜涨价排行 →</span>
            <span class="feature-example" @click.stop="$emit('quick', '近7天鸡蛋价格趋势')">近7天鸡蛋价格趋势 →</span>
          </div>
        </div>

        <div class="feature-card" @click="$emit('quick', '土豆最新价格')">
          <div class="feature-card-header">
            <el-icon :size="20" class="feature-icon query"><Search /></el-icon>
            <span class="feature-title">实时价格查询</span>
          </div>
          <p class="feature-desc">输入产品名称，即时获取最新报价</p>
          <div class="feature-examples">
            <span class="feature-example" @click.stop="$emit('quick', '土豆最新价格')">土豆最新价格 →</span>
            <span class="feature-example" @click.stop="$emit('quick', '花生油价格')">花生油价格 →</span>
          </div>
        </div>

        <div class="feature-card" @click="$emit('quick', '对比不同品牌线茄')">
          <div class="feature-card-header">
            <el-icon :size="20" class="feature-icon compare"><DataAnalysis /></el-icon>
            <span class="feature-title">智能比价对比</span>
          </div>
          <p class="feature-desc">多品牌、多品质横向对比，找到最优选择</p>
          <div class="feature-examples">
            <span class="feature-example" @click.stop="$emit('quick', '对比不同品牌线茄')">对比不同品牌线茄 →</span>
            <span class="feature-example" @click.stop="$emit('quick', '对比不同品牌食用油价格')">对比食用油价格 →</span>
          </div>
        </div>
      </div>
    </div>

    <TransitionGroup name="msg" tag="div">
      <div v-for="msg in chatStore.messages" :key="msg.id" :class="['message', msg.role]">
        <!-- 用户消息 -->
        <template v-if="msg.role === 'user'">
          <div class="user-row">
            <el-tooltip content="回滚到此处重新提问" placement="top">
              <el-icon
                class="rollback-btn"
                :class="{ disabled: chatStore.loading }"
                @click="handleRollback(msg)"
              ><RefreshLeft /></el-icon>
            </el-tooltip>
            <div class="user-bubble">
              <div class="message-content">{{ msg.content }}</div>
            </div>
          </div>
        </template>

        <!-- AI 消息 -->
        <template v-else>
          <div class="ai-message">
            <!-- 上方：动态耗时 -->
            <div class="message-elapsed" v-if="isLastMessage(msg) && chatStore.streaming">
              已处理 {{ elapsedTime }}
            </div>
            <div class="message-elapsed" v-else-if="msg.duration">
              已处理 {{ formatDuration(msg.duration) }}
            </div>
            <!-- 工具调用步骤 -->
            <div v-if="msg.toolCalls && msg.toolCalls.length" class="tool-calls">
              <div v-for="(tool, idx) in msg.toolCalls" :key="idx" class="tool-call-item">
                <el-icon v-if="tool.status === 'done'" class="tool-call-icon done" :size="13"><Select /></el-icon>
                <el-icon v-else class="tool-call-icon running" :size="13"><Loading /></el-icon>
                <span class="tool-call-name">{{ tool.displayName }}</span>
              </div>
            </div>
            <!-- 工具调用中状态（仅在没有 toolCalls 列表时显示） -->
            <div
              v-if="isLastMessage(msg) && chatStore.toolStatus && !msg.content && !msg.thinking && !(msg.toolCalls && msg.toolCalls.length)"
              class="tool-status"
            >
              <el-icon class="tool-icon" :size="14"><Loading /></el-icon>
              <span class="tool-text">{{ chatStore.toolStatus }}</span>
            </div>
            <!-- 思考过程 -->
            <div v-if="msg.thinking" class="thinking-block">
              <div class="thinking-header" @click="toggleThinking(msg.id)">
                <el-icon class="thinking-icon" :size="14"><MagicStick /></el-icon>
                <span class="thinking-label">思考过程</span>
                <span class="thinking-toggle">{{ thinkingExpanded[msg.id] ? '收起' : '展开' }}</span>
              </div>
              <div v-show="thinkingExpanded[msg.id]" class="thinking-content" v-html="renderMarkdown(msg.thinking)"></div>
            </div>
            <!-- 正文 -->
            <div
              v-if="msg.content"
              class="message-content markdown-body"
              v-html="renderMarkdown(msg.content)"
              @click="handleContentClick"
            ></div>
            <!-- 光标 -->
            <span v-if="isLastMessage(msg) && chatStore.streaming && msg.content" class="cursor">|</span>
            <!-- 建议 -->
            <div v-if="msg.suggestions && msg.suggestions.length && isLastMessage(msg)" class="message-suggestions">
              <el-button
                v-for="s in msg.suggestions"
                :key="s"
                size="small"
                round
                class="suggestion-btn"
                @click="$emit('quick', s)"
              >
                {{ s }}
              </el-button>
            </div>
            <!-- 下方：完成时间 -->
            <div class="message-time" v-if="msg.duration && (!isLastMessage(msg) || !chatStore.streaming)">
              {{ formatTime(msg.timestamp) }}
            </div>
          </div>
        </template>
      </div>
    </TransitionGroup>

    <!-- 产品详情弹窗 -->
    <el-drawer v-model="productDrawerVisible" :title="`商品详情 - ${productDrawerName}`" size="600px">
      <div class="product-drawer-content">
        <!-- 商品基础信息 -->
        <div class="product-info-card" v-if="productInfo">
          <div class="product-info-grid">
            <div class="info-item">
              <span class="info-label">商品ID</span>
              <span class="info-value">{{ productInfo.product_id }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">商品名称</span>
              <span class="info-value">{{ productInfo.product_name }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">品牌</span>
              <span class="info-value">{{ productInfo.brand || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">品质</span>
              <span class="info-value">{{ productInfo.quality || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">规格</span>
              <span class="info-value">{{ productInfo.spec || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">分类</span>
              <span class="info-value">{{ productInfo.category_name || '-' }}</span>
            </div>
            <div class="info-item" v-if="productInfo.latest_price">
              <span class="info-label">最新价格</span>
              <span class="info-value price-highlight">¥{{ productInfo.latest_price.price }}/{{ productInfo.latest_price.unit }}
                <span class="price-date">（{{ productInfo.latest_price.date }}）</span>
              </span>
            </div>
          </div>
        </div>
        <el-skeleton v-else :rows="3" animated style="margin-bottom: 16px" />

        <!-- 价格趋势 -->
        <div class="price-section-title">历史价格趋势</div>
        <div class="price-toolbar">
          <el-radio-group v-model="productDays" size="small" @change="loadProductPrices">
            <el-radio-button :value="7">近一周</el-radio-button>
            <el-radio-button :value="30">近一月</el-radio-button>
            <el-radio-button :value="90">近三月</el-radio-button>
          </el-radio-group>
        </div>
        <div ref="productChartRef" class="product-chart"></div>
        <el-table :data="productPricesReversed" stripe size="small" max-height="250">
          <el-table-column prop="date" label="日期" min-width="110" />
          <el-table-column label="价格">
            <template #default="{ row }">¥{{ row.price }}/{{ row.unit }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, watch, onUnmounted, computed } from "vue"
import MarkdownIt from "markdown-it"
import { Loading, MagicStick, Select, TrendCharts, Search, DataAnalysis, RefreshLeft } from "@element-plus/icons-vue"
import { ElMessageBox } from "element-plus"
import * as echarts from "echarts"
import { useChatStore } from "../../stores/chat"
import request from "../../api/request"
import type { ChatMessage } from "../../types/message"

const chatStore = useChatStore()
const listRef = ref<HTMLElement>()
const thinkingExpanded = reactive<Record<string, boolean>>({})
const elapsedTime = ref("0s")
let elapsedTimer: ReturnType<typeof setInterval> | null = null

// 产品详情弹窗
const productDrawerVisible = ref(false)
const productDrawerName = ref("")
const productDrawerId = ref(0)
const productDays = ref(30)
const productPrices = ref<any[]>([])
// 表格倒序展示（最新日期在上）；趋势图仍用正序的 productPrices
const productPricesReversed = computed(() => [...productPrices.value].reverse())
const productInfo = ref<any>(null)
const productChartRef = ref<HTMLElement>()
let productChart: echarts.ECharts | null = null

// 动态计时器：streaming 时每秒更新
watch(() => chatStore.streaming, (streaming) => {
  if (streaming) {
    const msgs = chatStore.messages
    const lastMsg = msgs[msgs.length - 1]
    const startTs = lastMsg?.timestamp || Date.now()
    elapsedTimer = setInterval(() => {
      const elapsed = Date.now() - startTs
      elapsedTime.value = formatDuration(elapsed)
    }, 1000)
    // 立即更新一次
    elapsedTime.value = "0s"
  } else {
    if (elapsedTimer) {
      clearInterval(elapsedTimer)
      elapsedTimer = null
    }
  }
})

onUnmounted(() => {
  if (elapsedTimer) clearInterval(elapsedTimer)
  productChart?.dispose()
})

const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
})

const emit = defineEmits<{
  quick: [question: string]
  rollback: [content: string]
}>()

function isLastMessage(msg: ChatMessage): boolean {
  const msgs = chatStore.messages
  return msgs.length > 0 && msgs[msgs.length - 1].id === msg.id
}

/** 回滚到某条用户消息：删除它及之后的所有对话，并把内容回填到输入框 */
async function handleRollback(msg: ChatMessage) {
  if (chatStore.loading) return
  try {
    await ElMessageBox.confirm(
      "将删除这条消息及其之后的所有对话内容，并把它放回输入框，确定回滚吗？",
      "回滚对话",
      { confirmButtonText: "回滚", cancelButtonText: "取消", type: "warning" }
    )
  } catch {
    return
  }
  const content = await chatStore.rollbackTo(msg)
  if (content) emit("rollback", content)
}

function toggleThinking(msgId: string) {
  thinkingExpanded[msgId] = !thinkingExpanded[msgId]
}

/**
 * 渲染 Markdown，并将产品名转为可点击的 span。
 *
 * 后端工具返回 {#id=12345} 标记，LLM 被要求在最终回复中保留。
 * 策略：先渲染 markdown，再在 HTML 结果中找到 {#id=数字} 并把前面的产品名包成链接。
 */
function renderMarkdown(content: string): string {
  if (!content) return ""

  // 先正常渲染 markdown
  let html = md.render(content)

  // 把 {#id=N} 标记渲染成可点击产品名（兼容模型偶发的双括号 {{#id=N}}）。
  const markerLink = (productId: string, inner: string) =>
    `<span class="product-link" data-product-id="${productId}" title="点击查看价格详情">${inner}</span>`

  // 情况一：商品名被行内强调标签包裹，如 <strong>大西瓜</strong>{#id=123}。
  // 这种情况下标记前的纯文本为空，需先单独处理，否则会被情况二误删。
  html = html.replace(
    /<(strong|em|b|i)>([^<>]+?)<\/\1>\{{1,2}#id=(\d+)\}{1,2}/g,
    (_m, tag, inner, productId) => `<${tag}>${markerLink(productId, inner.trim())}</${tag}>`,
  )

  // 情况二：商品名为紧贴标记的纯文本。
  // 标记可能出现在 <td>、<li>、<p> 等元素内部。
  html = html.replace(
    /([^<>{}\n]*?)\{{1,2}#id=(\d+)\}{1,2}/g,
    (_match, textBefore, productId) => {
      const name = textBefore.trim()
      // 标记前无可用文本（已被情况一处理，或模型把标记单独放置）→ 仅移除标记，避免残留 {}
      if (!name) return ''

      // 如果产品名尾部带了价格（"大西瓜 - 1.53元/斤" / "大西瓜：1.53 元/斤"），分离出来，
      // 只把商品名做成链接。分隔符兼容 - – — : ：，数字与"元"之间允许空格。
      const priceMatch = name.match(/^(.+?)\s*[-–—:：]\s*([\d.]+\s*元\/.+)$/)
      if (priceMatch) {
        return `${markerLink(productId, priceMatch[1].trim())} - ${priceMatch[2].trim()}`
      }

      // 没有价格部分，整个作为链接
      return markerLink(productId, name)
    },
  )

  return html
}

/**
 * 处理 AI 消息内容区域的点击事件（事件委托）
 */
function handleContentClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.classList.contains("product-link")) {
    const productId = target.dataset.productId
    const productName = target.textContent || ""
    if (productId) {
      openProductDrawerById(parseInt(productId), productName)
    }
  }
}

/**
 * 通过 product_id 直接打开价格详情弹窗（无需搜索）
 */
async function openProductDrawerById(id: number, name: string) {
  productDrawerId.value = id
  productDrawerName.value = name
  productDrawerVisible.value = true
  productDays.value = 30
  productInfo.value = null
  productPrices.value = []

  // 并行加载商品信息和价格数据
  await Promise.all([loadProductInfo(), loadProductPrices()])
}

/**
 * 加载商品基础信息
 */
async function loadProductInfo() {
  if (!productDrawerId.value) return
  try {
    const res: any = await request.get("/admin/products", {
      params: { keyword: String(productDrawerId.value), page: 1, page_size: 1 },
    })
    if (res.products && res.products.length > 0) {
      productInfo.value = res.products[0]
      productDrawerName.value = res.products[0].product_name
    }
  } catch {
    productInfo.value = null
  }
}

async function loadProductPrices() {
  if (!productDrawerId.value) return
  try {
    const res: any = await request.get(`/admin/products/${productDrawerId.value}/prices`, {
      params: { days: productDays.value },
    })
    productPrices.value = res.prices
    await nextTick()
    renderProductChart()
  } catch {
    productPrices.value = []
  }
}

function renderProductChart() {
  if (!productChartRef.value) return

  if (!productChart) {
    productChart = echarts.init(productChartRef.value)
  }

  const dates = productPrices.value.map((p: any) => p.date)
  const prices = productPrices.value.map((p: any) => p.price)
  const unit = productPrices.value[0]?.unit || ""

  productChart.setOption({
    tooltip: {
      trigger: "axis",
      formatter: (params: any) => {
        const p = params[0]
        return `${p.axisValue}<br/>价格: ¥${p.value}/${unit}`
      },
    },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { fontSize: 11, rotate: dates.length > 15 ? 45 : 0 },
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 11, formatter: (v: number) => `¥${v}` },
    },
    series: [{
      type: "line",
      data: prices,
      smooth: true,
      symbol: "circle",
      symbolSize: 4,
      lineStyle: { color: "#409eff", width: 2 },
      itemStyle: { color: "#409eff" },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "rgba(64, 158, 255, 0.2)" },
          { offset: 1, color: "rgba(64, 158, 255, 0.02)" },
        ]),
      },
    }],
  })
  productChart.resize()
}

function formatTime(ts: number) {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainSeconds = seconds % 60
  return `${minutes}m ${remainSeconds}s`
}

function scrollToBottom() {
  nextTick(() => {
    const scrollContainer = listRef.value?.parentElement
    if (scrollContainer) {
      scrollContainer.scrollTop = scrollContainer.scrollHeight
    }
  })
}

watch(
  () => {
    const msgs = chatStore.messages
    if (msgs.length === 0) return ""
    const last = msgs[msgs.length - 1]
    return last.thinking || ""
  },
  () => {
    // 思考内容默认折叠：不自动展开，用户可点"展开"查看。仅保持滚动跟随。
    scrollToBottom()
  }
)

watch(() => chatStore.messages.length, () => { scrollToBottom() })
watch(
  () => {
    const msgs = chatStore.messages
    if (msgs.length === 0) return ""
    return msgs[msgs.length - 1].content
  },
  () => { scrollToBottom() }
)
watch(() => chatStore.toolStatus, () => { scrollToBottom() })
watch(() => chatStore.loading, () => { scrollToBottom() })
</script>

<style scoped>
.message-list {
  max-width: 800px;
  margin: 0 auto;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  padding-bottom: 16px;
}

/* ===== Welcome ===== */
.welcome {
  text-align: center;
  padding: 60px 20px 40px;
  max-width: 860px;
  margin: 0 auto;
}

.welcome-icon {
  margin-bottom: 20px;
}

.welcome-logo {
  width: 56px;
  height: 56px;
  border-radius: 14px;
}

.welcome h2 {
  color: #1a1a1a;
  margin-bottom: 8px;
  font-size: 24px;
  font-weight: 700;
}

.welcome-desc {
  font-size: 14px;
  color: #909399;
  margin-bottom: 36px;
}

.feature-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  text-align: left;
}.feature-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.25s;
}

.feature-card:hover {
  border-color: #d9ecff;
  box-shadow: 0 4px 16px rgba(64, 158, 255, 0.08);
  transform: translateY(-2px);
}

.feature-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.feature-icon {
  padding: 6px;
  border-radius: 8px;
}

.feature-icon.price { color: #409eff; background: #ecf5ff; }
.feature-icon.query { color: #67c23a; background: #f0f9eb; }
.feature-icon.compare { color: #e6a23c; background: #fdf6ec; }

.feature-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.feature-desc {
  font-size: 12px;
  color: #909399;
  margin: 0 0 12px;
  line-height: 1.5;
}

.feature-examples {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.feature-example {
  font-size: 12px;
  color: #606266;
  padding: 6px 10px;
  background: #f7f8fa;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.feature-example:hover {
  background: #ecf5ff;
  color: #409eff;
}

/* ===== Messages ===== */
.message {
  margin-bottom: 24px;
}

.message.user {
  display: flex;
  justify-content: flex-end;
}

/* 用户消息行：回滚按钮 + 气泡 */
.user-row {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 70%;
}

.rollback-btn {
  font-size: 15px;
  color: #c0c4cc;
  cursor: pointer;
  opacity: 0;
  flex-shrink: 0;
  transition: opacity 0.2s, color 0.2s;
}

.user-row:hover .rollback-btn {
  opacity: 1;
}

.rollback-btn:hover {
  color: #409eff;
}

.rollback-btn.disabled {
  cursor: not-allowed;
  opacity: 0;
}

/* User bubble */
.user-bubble {
  max-width: 100%;
  padding: 10px 16px;
  background: #e8f4ff;
  color: #303133;
  border-radius: 18px 18px 4px 18px;
  font-size: 14px;
  line-height: 1.6;
  border: 1px solid #d9ecff;
}

.user-bubble .message-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.user-bubble .message-time {
  font-size: 11px;
  color: #a8abb2;
  margin-top: 4px;
  text-align: right;
}

/* AI message - no bubble, direct content */
.ai-message {
  padding: 4px 0;
  line-height: 1.7;
  font-size: 14px;
  color: #303133;
}

.ai-message .message-time {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 10px;
}

.message-elapsed {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.message-duration {
  font-size: 12px;
  color: #a8abb2;
  margin-top: 10px;
}

/* Tool status */
.tool-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 13px;
  color: #909399;
}

.tool-icon {
  color: #409eff;
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.tool-text {
  color: #606266;
}

/* Tool call steps */
.tool-calls {
  padding: 4px 0 8px;
  margin-bottom: 4px;
}

.tool-call-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 13px;
  color: #909399;
}

.tool-call-icon.done { color: #67c23a; }
.tool-call-icon.running {
  color: #409eff;
  animation: spin 1.5s linear infinite;
}

.tool-call-name { color: #606266; }

/* Thinking block */
.thinking-block {
  margin-bottom: 12px;
  border: 1px solid #fde2c8;
  border-radius: 8px;
  background: #fef9f3;
  overflow: hidden;
  word-break: break-word;
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.thinking-header:hover { background: #fdf0e0; }
.thinking-icon { color: #e6a23c; }

.thinking-label {
  font-size: 12px;
  font-weight: 500;
  color: #e6a23c;
  flex: 1;
}

.thinking-toggle {
  font-size: 11px;
  color: #c0c4cc;
}

.thinking-content {
  padding: 8px 12px 10px;
  font-size: 12px;
  line-height: 1.6;
  color: #8c8c8c;
  max-height: 500px;
  overflow-y: auto;
  overflow-x: hidden;
  border-top: 1px solid #fde2c8;
  word-break: break-word;
  overflow-wrap: break-word;
}

.thinking-content::-webkit-scrollbar {
  width: 4px;
}

.thinking-content::-webkit-scrollbar-track {
  background: transparent;
}

.thinking-content::-webkit-scrollbar-thumb {
  background: #f0d4b8;
  border-radius: 2px;
}

.thinking-content::-webkit-scrollbar-thumb:hover {
  background: #e6b88a;
}

.thinking-content :deep(p) { margin: 0 0 6px; word-break: break-word; }
.thinking-content :deep(p:last-child) { margin-bottom: 0; }
.thinking-content :deep(ul),
.thinking-content :deep(ol) { padding-left: 18px; margin: 4px 0; }
.thinking-content :deep(li) { margin: 2px 0; word-break: break-word; }

/* Cursor */
.cursor {
  animation: blink 1s step-end infinite;
  color: #409eff;
  font-weight: 300;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* Message content & Markdown */
.message-content {
  word-break: break-word;
  font-size: 14px;
}

.markdown-body :deep(p) { margin: 0 0 8px; }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 6px 0; padding-left: 20px; }
.markdown-body :deep(li) { margin: 3px 0; }
.markdown-body :deep(strong) { font-weight: 600; color: #1a1a1a; }
.markdown-body :deep(em) { font-style: italic; color: #606266; }

.markdown-body :deep(code) {
  background: #f4f4f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: #e6a23c;
}

.markdown-body :deep(pre) {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-body :deep(pre code) { background: none; padding: 0; color: #303133; }

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) { margin: 12px 0 6px; font-weight: 600; color: #1a1a1a; }
.markdown-body :deep(h1) { font-size: 18px; }
.markdown-body :deep(h2) { font-size: 16px; }
.markdown-body :deep(h3) { font-size: 15px; }

.markdown-body :deep(blockquote) {
  border-left: 3px solid #409eff;
  padding-left: 12px;
  margin: 8px 0;
  color: #606266;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #ebeef5;
  padding: 6px 10px;
  text-align: left;
}

.markdown-body :deep(th) { background: #f5f7fa; font-weight: 600; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid #ebeef5; margin: 12px 0; }
.markdown-body :deep(a) { color: #409eff; text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }

/* Cards & Suggestions */
.message-suggestions {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.suggestion-btn {
  font-size: 12px;
  border-color: #d9ecff;
  color: #409eff;
  background: #f0f9ff;
}

.suggestion-btn:hover {
  background: #ecf5ff;
  border-color: #409eff;
}

/* Transition */
.msg-enter-active { transition: all 0.3s ease; }
.msg-enter-from { opacity: 0; transform: translateY(12px); }

/* Product link - clickable product names in AI responses */
.markdown-body :deep(.product-link) {
  color: #409eff;
  cursor: pointer;
  border-bottom: 1px dashed #409eff;
  transition: all 0.2s;
  font-weight: 500;
}

.markdown-body :deep(.product-link:hover) {
  color: #66b1ff;
  border-bottom-color: #66b1ff;
  background: #ecf5ff;
  border-radius: 2px;
  padding: 0 2px;
  margin: 0 -2px;
}

/* Product drawer */
.product-drawer-content {
  padding: 0 4px;
}

.product-info-card {
  background: #f9fafb;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 20px;
}

.product-info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 24px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.info-label {
  font-size: 11px;
  color: #909399;
  font-weight: 500;
}

.info-value {
  font-size: 13px;
  color: #303133;
  word-break: break-word;
}

.info-value.price-highlight {
  color: #409eff;
  font-weight: 600;
  font-size: 14px;
}

.price-date {
  font-size: 11px;
  color: #909399;
  font-weight: normal;
}

.price-section-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 12px;
}

.price-toolbar {
  margin-bottom: 16px;
}

.product-chart {
  width: 100%;
  height: 240px;
  margin-bottom: 16px;
}

/* ===== Mobile ===== */
@media (max-width: 768px) {
  .welcome {
    padding: 32px 12px 24px;
  }

  .welcome h2 {
    font-size: 20px;
  }

  .welcome-desc {
    font-size: 13px;
    margin-bottom: 24px;
  }

  .feature-cards {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .feature-card {
    padding: 16px;
  }

  .user-bubble {
    max-width: 85%;
    font-size: 13px;
  }

  .ai-message {
    font-size: 13px;
  }

  .markdown-body :deep(table) {
    font-size: 12px;
  }

  .markdown-body :deep(pre) {
    font-size: 12px;
  }

  .message-suggestions {
    gap: 4px;
  }

  .suggestion-btn {
    font-size: 11px;
    padding: 4px 10px;
  }
}
</style>
