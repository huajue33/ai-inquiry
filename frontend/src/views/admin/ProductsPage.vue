<template>
  <div class="admin-page">
    <h2>商品管理</h2>
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索商品名称" style="width: 220px" @keyup.enter="handleSearch">
        <template #append>
          <el-button @click="handleSearch"><el-icon><Search /></el-icon></el-button>
        </template>
      </el-input>
      <el-cascader
        v-model="selectedCategory"
        :options="categoryTree"
        :props="{ value: 'id', label: 'name', children: 'children', checkStrictly: true, emitPath: true }"
        placeholder="选择分类"
        clearable
        style="width: 280px"
        @change="handleCategoryChange"
      />
    </div>
    <el-table :data="products" stripe style="width: 100%">
      <el-table-column prop="product_id" label="ID" min-width="90" />
      <el-table-column prop="product_name" label="产品名称" min-width="200" />
      <el-table-column prop="brand" label="品牌" min-width="100" />
      <el-table-column prop="category_name" label="分类" min-width="140" />
      <el-table-column prop="quality" label="品质" min-width="70" />
      <el-table-column prop="spec" label="规格" min-width="100" />
      <el-table-column label="最新价格" min-width="130">
        <template #default="{ row }">
          <span v-if="row.latest_price" class="price-text">¥{{ row.latest_price.price }}/{{ row.latest_price.unit }}</span>
          <span v-else class="no-price">暂无</span>
        </template>
      </el-table-column>
      <el-table-column label="价格日期" min-width="110">
        <template #default="{ row }">
          <span v-if="row.latest_price" class="date-text">{{ row.latest_price.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="90">
        <template #default="{ row }">
          <el-button text size="small" type="primary" @click="viewPriceHistory(row.product_id, row.product_name)">历史价格</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="pagination"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="20"
      :current-page="page"
      @current-change="(p: number) => { page = p; loadProducts() }"
    />

    <!-- 历史价格抽屉 -->
    <el-drawer v-model="drawerVisible" :title="`历史价格 - ${priceProductName}`" size="680px">
      <div class="drawer-content">
        <div class="price-toolbar">
          <el-radio-group v-model="priceDays" size="small" @change="loadPriceHistory">
            <el-radio-button :value="7">近一周</el-radio-button>
            <el-radio-button :value="30">近一月</el-radio-button>
            <el-radio-button :value="365">近一年</el-radio-button>
          </el-radio-group>
        </div>
        <div ref="chartRef" class="price-chart"></div>
        <el-table :data="priceHistory" stripe style="width: 100%" max-height="300" size="small" class="price-table">
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
import { ref, nextTick, onMounted, onUnmounted } from "vue"
import { Search } from "@element-plus/icons-vue"
import * as echarts from "echarts"
import request from "../../api/request"

interface CategoryNode {
  id: number
  name: string
  children?: CategoryNode[]
}

const products = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const keyword = ref("")
const selectedCategory = ref<number[]>([])
const categoryTree = ref<CategoryNode[]>([])

const drawerVisible = ref(false)
const priceProductName = ref("")
const priceProductId = ref(0)
const priceDays = ref(30)
const priceHistory = ref<any[]>([])
const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

onMounted(() => {
  loadProducts()
  loadCategories()
})

onUnmounted(() => {
  chartInstance?.dispose()
})

function handleSearch() {
  page.value = 1
  loadProducts()
}

function handleCategoryChange(val: number[] | null) {
  selectedCategory.value = val || []
  handleSearch()
}

async function loadCategories() {
  try {
    const res: any = await request.get("/admin/categories")
    categoryTree.value = buildTree(res.categories)
  } catch { /* ignore */ }
}

function buildTree(categories: any[]): CategoryNode[] {
  const map = new Map<number, CategoryNode>()
  const roots: CategoryNode[] = []

  for (const cat of categories) {
    map.set(cat.id, { id: cat.id, name: cat.name, children: [] })
  }

  for (const cat of categories) {
    const node = map.get(cat.id)!
    if (cat.parent_id && map.has(cat.parent_id)) {
      map.get(cat.parent_id)!.children!.push(node)
    } else {
      roots.push(node)
    }
  }

  // 移除空 children
  function clean(nodes: CategoryNode[]) {
    for (const n of nodes) {
      if (n.children && n.children.length === 0) {
        delete n.children
      } else if (n.children) {
        clean(n.children)
      }
    }
  }
  clean(roots)
  return roots
}

async function loadProducts() {
  try {
    // 取级联选择器最后一级的 ID
    const categoryId = selectedCategory.value.length > 0
      ? selectedCategory.value[selectedCategory.value.length - 1]
      : undefined
    const res: any = await request.get("/admin/products", {
      params: { keyword: keyword.value, page: page.value, page_size: 20, category_id: categoryId },
    })
    products.value = res.products
    total.value = res.total
  } catch { /* ignore */ }
}

async function viewPriceHistory(productId: number, productName: string) {
  priceProductId.value = productId
  priceProductName.value = productName
  priceDays.value = 30
  drawerVisible.value = true
  await loadPriceHistory()
}

async function loadPriceHistory() {
  try {
    const res: any = await request.get(`/admin/products/${priceProductId.value}/prices`, { params: { days: priceDays.value } })
    priceHistory.value = res.prices
    await nextTick()
    renderChart()
  } catch { /* ignore */ }
}

function renderChart() {
  if (!chartRef.value) return

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const dates = priceHistory.value.map(p => p.date)
  const prices = priceHistory.value.map(p => p.price)
  const unit = priceHistory.value[0]?.unit || ""

  chartInstance.setOption({
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
  chartInstance.resize()
}
</script>

<style scoped>
.admin-page { padding: 24px; }
.admin-page h2 { font-size: 18px; font-weight: 600; color: #303133; margin: 0 0 20px; }
.toolbar { margin-bottom: 16px; display: flex; gap: 12px; align-items: center; }
.pagination { margin-top: 16px; justify-content: flex-end; }
.price-text { color: #409eff; font-weight: 500; }
.no-price { color: #c0c4cc; font-size: 12px; }
.date-text { color: #909399; font-size: 12px; }

.drawer-content {
  padding: 0 4px;
  height: 100%;
  overflow-y: auto;
}

.price-toolbar { margin-bottom: 16px; }
.price-chart { width: 100%; height: 260px; margin-bottom: 16px; }
.price-table { margin-top: 8px; }
</style>
