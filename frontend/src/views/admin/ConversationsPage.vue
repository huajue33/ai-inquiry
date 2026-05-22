<template>
  <div class="admin-page">
    <h2>对话记录</h2>
    <el-table :data="convList" stripe style="width: 100%">
      <el-table-column prop="user_id" label="用户ID" min-width="70" />
      <el-table-column prop="user_name" label="用户" min-width="100" />
      <el-table-column prop="title" label="标题" min-width="180" />
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
          <div v-for="msg in messages" :key="msg.id" :class="['conv-msg', msg.role]">
            <div class="conv-msg-header">
              <span class="conv-msg-role">{{ msg.role === 'user' ? '用户' : 'AI' }}</span>
              <span class="conv-msg-meta">
                <span v-if="msg.total_tokens" class="conv-msg-tokens">
                  入：{{ msg.prompt_tokens }} | 出：{{ msg.completion_tokens }} | 总：{{ msg.total_tokens }}
                </span>
                <span class="conv-msg-time">{{ msg.created_at }}</span>
              </span>
            </div>
            <div v-if="msg.role === 'assistant'" class="conv-msg-content markdown-body" v-html="renderMarkdown(msg.content)"></div>
            <div v-else class="conv-msg-content">{{ msg.content }}</div>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import MarkdownIt from "markdown-it"
import request from "../../api/request"

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

const convList = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const dialogVisible = ref(false)
const messages = ref<any[]>([])

onMounted(() => { loadConversations() })

function renderMarkdown(content: string): string {
  if (!content) return ""
  return md.render(content)
}

async function loadConversations() {
  try {
    const res: any = await request.get("/admin/conversations", { params: { page: page.value, page_size: 20 } })
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
.pagination { margin-top: 16px; justify-content: flex-end; }

.conv-messages {
  height: 100%;
  overflow-y: auto;
  padding: 0 4px;
}

.conv-messages::-webkit-scrollbar {
  width: 5px;
}

.conv-messages::-webkit-scrollbar-track {
  background: transparent;
}

.conv-messages::-webkit-scrollbar-thumb {
  background: #e4e7ed;
  border-radius: 3px;
}

.conv-messages::-webkit-scrollbar-thumb:hover {
  background: #c0c4cc;
}

.conv-msg {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 8px;
}

.conv-msg.user { background: #ecf5ff; }
.conv-msg.assistant { background: #f9fafb; }

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
