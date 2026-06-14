<template>
  <div class="admin-page">
    <h2>{{ isAdmin ? "对话记录" : "我的对话记录" }}</h2>

    <!-- 搜索工具栏 -->
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索对话标题或消息内容"
        style="width: 280px"
        clearable
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #append>
          <el-button @click="handleSearch"><el-icon><Search /></el-icon></el-button>
        </template>
      </el-input>
      <el-select
        v-if="isAdmin"
        v-model="filterUserId"
        placeholder="筛选用户"
        clearable
        filterable
        style="width: 180px"
        @change="handleSearch"
      >
        <el-option
          v-for="u in userList"
          :key="u.id"
          :label="`${u.real_name} (${u.username})`"
          :value="u.id"
        />
      </el-select>
      <el-tag v-if="keyword || filterUserId" type="info" closable @close="clearFilters">
        {{ filterSummary }}
      </el-tag>
    </div>

    <el-table :data="convList" stripe style="width: 100%">
      <el-table-column v-if="isAdmin" prop="user_id" label="用户ID" min-width="70" />
      <el-table-column v-if="isAdmin" prop="user_name" label="用户" min-width="100" />
      <el-table-column prop="title" label="标题" min-width="180">
        <template #default="{ row }">
          <span v-html="highlightKeyword(row.title)"></span>
        </template>
      </el-table-column>
      <el-table-column prop="message_count" label="消息数" min-width="80" />
      <el-table-column prop="token_count" label="Token消耗" min-width="100">
        <template #default="{ row }">
          <span v-if="row.token_count">{{ row.token_count.toLocaleString() }}</span>
          <span v-else class="no-data">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="is_deleted" label="状态" min-width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_deleted ? 'danger' : 'success'" size="small">
            {{ row.is_deleted ? '已删除' : '正常' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="170" />
      <el-table-column label="操作" min-width="80">
        <template #default="{ row }">
          <el-button text size="small" @click="viewConversation(row.id)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="pagination"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="20"
      :current-page="page"
      @current-change="(p: number) => { page = p; loadConversations() }"
    />

    <el-drawer v-model="dialogVisible" title="对话详情" size="680px">
      <template #default>
        <div class="conv-messages">
          <div v-for="msg in messages" :key="msg.id" :class="['conv-msg', msg.role, { 'rolled-back': msg.is_rolled_back }]">
            <div class="conv-msg-header">
              <span class="conv-msg-role">{{ msg.role === 'user' ? '用户' : 'AI' }}</span>
              <span class="conv-msg-meta">
                <el-tag v-if="msg.is_rolled_back" type="info" size="small" effect="plain">已回滚</el-tag>
                <span v-if="msg.total_tokens" class="conv-msg-tokens">
                  入：{{ msg.prompt_tokens }} | 出：{{ msg.completion_tokens }} | 总：{{ msg.total_tokens }}
                </span>
                <span class="conv-msg-time">{{ msg.created_at }}</span>
              </span>
            </div>
            <div v-if="msg.role === 'assistant'" class="conv-msg-content markdown-body" v-html="renderMarkdown(msg.content)"></div>
            <div v-else class="conv-msg-content" v-html="highlightKeyword(msg.content)"></div>

            <!-- Agent 执行流程：每次工具调用的入参与返回结果 -->
            <div v-if="msg.role === 'assistant' && msg.tool_trace && msg.tool_trace.length" class="conv-trace">
              <el-collapse>
                <el-collapse-item :title="`Agent 执行流程（${msg.tool_trace.length} 次工具调用）`">
                  <div v-for="(t, i) in msg.tool_trace" :key="i" class="trace-step">
                    <div class="trace-step-head">
                      <span class="trace-idx">{{ Number(i) + 1 }}</span>
                      <span class="trace-tool">{{ t.tool }}</span>
                      <el-tag :type="traceTagType(t.status)" size="small">{{ t.status || '-' }}</el-tag>
                      <span v-if="t.duration_ms != null" class="trace-dur">{{ fmtMs(t.duration_ms) }}</span>
                    </div>
                    <div class="trace-block">
                      <div class="trace-label">入参</div>
                      <pre class="trace-pre">{{ pretty(t.args) }}</pre>
                    </div>
                    <div class="trace-block">
                      <div class="trace-label">返回</div>
                      <pre class="trace-pre">{{ pretty(t.result) }}</pre>
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { Search } from "@element-plus/icons-vue"
import MarkdownIt from "markdown-it"
import request from "../../api/request"

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

const currentUser = JSON.parse(localStorage.getItem("user") || '{"role":""}')
const isAdmin = computed(() => currentUser.role === "admin")

const convList = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const keyword = ref("")
const filterUserId = ref<number | undefined>(undefined)
const userList = ref<any[]>([])
const dialogVisible = ref(false)
const messages = ref<any[]>([])

const filterSummary = computed(() => {
  const parts: string[] = []
  if (keyword.value) parts.push(`关键词: "${keyword.value}"`)
  if (filterUserId.value) {
    const u = userList.value.find((u: any) => u.id === filterUserId.value)
    if (u) parts.push(`用户: ${u.real_name}`)
  }
  return parts.join(' | ')
})

onMounted(() => {
  loadConversations()
  if (isAdmin.value) loadUsers()
})

function renderMarkdown(content: string): string {
  if (!content) return ""
  return md.render(content)
}

/** 美化展示入参/返回：字符串若是 JSON 则缩进格式化，否则原样 */
function pretty(val: any): string {
  if (val == null || val === "") return "（空）"
  if (typeof val === "string") {
    try {
      return JSON.stringify(JSON.parse(val), null, 2)
    } catch {
      return val
    }
  }
  try {
    return JSON.stringify(val, null, 2)
  } catch {
    return String(val)
  }
}

/** 按工具状态给 tag 配色 */
function traceTagType(status: string): "success" | "info" | "danger" {
  if (status && status.startsWith("error")) return "danger"
  if (status === "empty") return "info"
  return "success"
}

/** 毫秒耗时格式化：<1s 显示 ms，否则显示 s */
function fmtMs(ms?: number): string {
  if (ms == null) return ""
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

function highlightKeyword(text: string): string {
  if (!text || !keyword.value.trim()) return text || ""
  const kw = keyword.value.trim()
  // 转义正则特殊字符
  const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  return text.replace(regex, '<mark class="search-highlight">$1</mark>')
}

function handleSearch() {
  page.value = 1
  loadConversations()
}

function clearFilters() {
  keyword.value = ""
  filterUserId.value = undefined
  handleSearch()
}

async function loadUsers() {
  try {
    const res: any = await request.get("/admin/users")
    userList.value = res.users || []
  } catch { /* ignore */ }
}

async function loadConversations() {
  try {
    const params: any = { page: page.value, page_size: 20 }
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (filterUserId.value) params.user_id = filterUserId.value
    const res: any = await request.get("/admin/conversations", { params })
    convList.value = res.conversations
    total.value = res.total
  } catch { /* ignore */ }
}

async function viewConversation(id: string) {
  try {
    const res: any = await request.get(`/admin/conversations/${id}/messages`)
    messages.value = res.messages
    dialogVisible.value = true
  } catch { /* ignore */ }
}
</script>

<style scoped>
.admin-page { padding: 24px; }
.admin-page h2 { font-size: 18px; font-weight: 600; color: #303133; margin: 0 0 20px; }
.toolbar { margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.pagination { margin-top: 16px; justify-content: flex-end; }

.conv-messages {
  height: 100%;
  overflow-y: auto;
  padding: 0 4px;
}

.conv-msg {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 8px;
}

.conv-msg.user { background: #ecf5ff; }
.conv-msg.assistant { background: #f9fafb; }

/* 已回滚消息：淡化展示，仍保留在审计记录中 */
.conv-msg.rolled-back {
  opacity: 0.55;
}

.conv-msg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.conv-msg-role {
  font-size: 12px;
  font-weight: 500;
  color: #909399;
}

.conv-msg-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.conv-msg-tokens {
  font-size: 11px;
  color: #e6a23c;
  background: #fdf6ec;
  padding: 1px 6px;
  border-radius: 3px;
}

.conv-msg-time {
  font-size: 11px;
  color: #c0c4cc;
}

.no-data {
  color: #c0c4cc;
  font-size: 12px;
}

.conv-msg-content {
  font-size: 13px;
  color: #303133;
  word-break: break-word;
  line-height: 1.7;
}

.conv-msg.user .conv-msg-content {
  white-space: pre-wrap;
}

/* Agent 执行流程 */
.conv-trace {
  margin-top: 10px;
}

.conv-trace :deep(.el-collapse-item__header) {
  font-size: 12px;
  color: #909399;
  height: 32px;
  line-height: 32px;
}

.trace-step {
  padding: 8px 0;
  border-bottom: 1px dashed #ebeef5;
}

.trace-step:last-child {
  border-bottom: none;
}

.trace-step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.trace-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ecf5ff;
  color: #409eff;
  font-size: 11px;
  flex-shrink: 0;
}

.trace-tool {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.trace-dur {
  font-size: 11px;
  color: #909399;
  background: #f0f2f5;
  padding: 1px 6px;
  border-radius: 3px;
}

.trace-block {
  margin: 4px 0;
}

.trace-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 2px;
}

.trace-pre {
  margin: 0;
  padding: 8px 10px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #303133;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Search highlight */
:deep(.search-highlight) {
  background: #fef3cd;
  color: #856404;
  padding: 0 2px;
  border-radius: 2px;
}

/* Markdown styles */
.markdown-body :deep(p) { margin: 0 0 8px; }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: 4px 0; padding-left: 18px; }
.markdown-body :deep(li) { margin: 2px 0; }
.markdown-body :deep(strong) { font-weight: 600; color: #1a1a1a; }
.markdown-body :deep(code) { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.markdown-body :deep(pre) { background: #f5f7fa; border-radius: 6px; padding: 10px; overflow-x: auto; margin: 6px 0; }
.markdown-body :deep(pre code) { background: none; padding: 0; }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 12px; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid #ebeef5; padding: 4px 8px; text-align: left; }
.markdown-body :deep(th) { background: #f5f7fa; font-weight: 600; }
.markdown-body :deep(blockquote) { border-left: 3px solid #409eff; padding-left: 10px; margin: 6px 0; color: #606266; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { margin: 10px 0 4px; font-weight: 600; }
.markdown-body :deep(h1) { font-size: 16px; }
.markdown-body :deep(h2) { font-size: 15px; }
.markdown-body :deep(h3) { font-size: 14px; }
</style>
