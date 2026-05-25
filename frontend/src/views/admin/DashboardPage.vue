<template>
  <div class="admin-page">
    <h2>
      数据概览
      <el-tag v-if="!isAdmin" size="small" type="info" class="scope-tag">仅显示我自己的数据</el-tag>
    </h2>

    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div v-if="isAdmin" class="stat-card">
        <div class="stat-icon users"><el-icon :size="24"><User /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_users }}</div>
          <div class="stat-label">用户总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon products"><el-icon :size="24"><Goods /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_products?.toLocaleString() }}</div>
          <div class="stat-label">商品总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon conversations"><el-icon :size="24"><ChatDotRound /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_conversations }}</div>
          <div class="stat-label">对话总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon messages"><el-icon :size="24"><Comment /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_messages }}</div>
          <div class="stat-label">消息总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon today"><el-icon :size="24"><TrendCharts /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.today_conversations }}</div>
          <div class="stat-label">今日对话</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon tokens"><el-icon :size="24"><Coin /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total_tokens?.toLocaleString() }}</div>
          <div class="stat-label">Token 总消耗</div>
        </div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="chart-section">
      <div class="chart-card">
        <h3>近7天对话趋势</h3>
        <div ref="convChartRef" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <h3>近7天 Token 消耗</h3>
        <div ref="tokenChartRef" class="chart-container"></div>
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-card full">
        <h3>近7天消息量</h3>
        <div ref="msgChartRef" class="chart-container"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, onUnmounted, nextTick } from "vue"
import { User, Goods, ChatDotRound, Comment, TrendCharts, Coin } from "@element-plus/icons-vue"
import * as echarts from "echarts"
import request from "../../api/request"

const currentUser = JSON.parse(localStorage.getItem("user") || '{"role":""}')
const isAdmin = computed(() => currentUser.role === "admin")

const stats = reactive<any>({
  total_users: 0,
  total_products: 0,
  total_conversations: 0,
  total_messages: 0,
  today_conversations: 0,
  total_tokens: 0,
  daily_conversations: [],
  daily_tokens: [],
  daily_messages: [],
})

const convChartRef = ref<HTMLElement>()
const tokenChartRef = ref<HTMLElement>()
const msgChartRef = ref<HTMLElement>()
let convChart: echarts.ECharts | null = null
let tokenChart: echarts.ECharts | null = null
let msgChart: echarts.ECharts | null = null

onMounted(async () => {
  try {
    const res: any = await request.get("/admin/stats")
    Object.assign(stats, res)
    await nextTick()
    renderCharts()
  } catch { /* ignore */ }
})

onUnmounted(() => {
  convChart?.dispose()
  tokenChart?.dispose()
  msgChart?.dispose()
})

function renderCharts() {
  // 对话趋势图
  if (convChartRef.value) {
    convChart = echarts.init(convChartRef.value)
    const dates = stats.daily_conversations.map((d: any) => d.date.slice(5))
    const counts = stats.daily_conversations.map((d: any) => d.count)
    convChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 20, top: 10, bottom: 24 },
      xAxis: { type: "category", data: dates, axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", minInterval: 1, axisLabel: { fontSize: 11 } },
      series: [{
        type: "bar",
        data: counts,
        itemStyle: { color: "#409eff", borderRadius: [4, 4, 0, 0] },
        barWidth: "40%",
      }],
    })
  }

  // Token 消耗图
  if (tokenChartRef.value) {
    tokenChart = echarts.init(tokenChartRef.value)
    const dates = stats.daily_tokens.map((d: any) => d.date.slice(5))
    const tokens = stats.daily_tokens.map((d: any) => d.tokens)
    tokenChart.setOption({
      tooltip: { trigger: "axis", formatter: (p: any) => `${p[0].axisValue}<br/>Token: ${p[0].value.toLocaleString()}` },
      grid: { left: 50, right: 20, top: 10, bottom: 24 },
      xAxis: { type: "category", data: dates, axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", axisLabel: { fontSize: 11 } },
      series: [{
        type: "line",
        data: tokens,
        smooth: true,
        symbol: "circle",
        symbolSize: 5,
        lineStyle: { color: "#e6a23c", width: 2 },
        itemStyle: { color: "#e6a23c" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(230, 162, 60, 0.2)" },
            { offset: 1, color: "rgba(230, 162, 60, 0.02)" },
          ]),
        },
      }],
    })
  }

  // 消息量图
  if (msgChartRef.value) {
    msgChart = echarts.init(msgChartRef.value)
    const dates = stats.daily_messages.map((d: any) => d.date.slice(5))
    const counts = stats.daily_messages.map((d: any) => d.count)
    msgChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 20, top: 10, bottom: 24 },
      xAxis: { type: "category", data: dates, axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", minInterval: 1, axisLabel: { fontSize: 11 } },
      series: [{
        type: "bar",
        data: counts,
        itemStyle: { color: "#67c23a", borderRadius: [4, 4, 0, 0] },
        barWidth: "40%",
      }],
    })
  }
}
</script>

<style scoped>
.admin-page {
  padding: 24px;
  overflow-y: auto;
  height: 100%;
}

.admin-page h2 {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 20px;
}

.scope-tag {
  margin-left: 12px;
  vertical-align: middle;
  font-weight: normal;
}

/* Stat cards */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  border: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon.users { background: #ecf5ff; color: #409eff; }
.stat-icon.products { background: #f0f9eb; color: #67c23a; }
.stat-icon.conversations { background: #fdf6ec; color: #e6a23c; }
.stat-icon.messages { background: #f4f4f5; color: #909399; }
.stat-icon.today { background: #ecf5ff; color: #6366f1; }
.stat-icon.tokens { background: #fef0f0; color: #f56c6c; }

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 2px;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

/* Chart section */
.chart-section {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.chart-card {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  border: 1px solid #ebeef5;
}

.chart-card.full {
  grid-column: 1 / -1;
}

.chart-card h3 {
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  margin: 0 0 12px;
}

.chart-container {
  width: 100%;
  height: 200px;
}
</style>
