<template>
  <div class="chat-layout">
    <!-- 移动端遮罩：点击关闭抽屉 -->
    <div
      v-if="isMobile && mobileSidebarOpen"
      class="mobile-mask"
      @click="mobileSidebarOpen = false"
    ></div>

    <!-- 左侧边栏 -->
    <aside :class="['sidebar', { collapsed: !isMobile && sidebarCollapsed, 'mobile-open': isMobile && mobileSidebarOpen, 'mobile-hidden': isMobile && !mobileSidebarOpen }]">
      <div class="sidebar-header">
        <!-- 折叠状态（仅桌面）：默认显示 logo，hover 侧边栏时显示展开按钮 -->
        <div v-if="!isMobile && sidebarCollapsed" class="logo-collapsed" @click="sidebarCollapsed = false">
          <img src="/favicon.svg" alt="logo" class="logo-img-collapsed" />
          <el-icon class="expand-icon" :size="18"><Expand /></el-icon>
        </div>
        <!-- 展开状态：正常显示 logo + 文字 + 折叠/关闭按钮 -->
        <template v-else>
          <img src="/favicon.svg" alt="logo" class="logo-img-static" />
          <span class="logo-text">AI 询价助手</span>
          <el-button
            text
            circle
            class="collapse-btn"
            @click="isMobile ? (mobileSidebarOpen = false) : (sidebarCollapsed = true)"
          >
            <el-icon :size="16">
              <Close v-if="isMobile" />
              <Fold v-else />
            </el-icon>
          </el-button>
        </template>
      </div>
      <div class="sidebar-action" v-show="isMobile || !sidebarCollapsed">
        <el-button type="primary" round class="new-chat-btn" @click="handleClear">
          <el-icon><Plus /></el-icon>
          <span>新建询价对话</span>
        </el-button>
      </div>
      <div class="sidebar-action" v-show="!isMobile && sidebarCollapsed">
        <el-tooltip content="新建对话" placement="right">
          <el-button type="primary" circle size="small" @click="handleClear">
            <el-icon><Plus /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
      <div class="sidebar-history" v-show="isMobile || !sidebarCollapsed">
        <div class="history-label">最近记录</div>
        <div class="history-list">
          <div
            v-for="conv in visibleConversations"
            :key="conv.id"
            :class="['history-item', { active: conv.id === chatStore.conversationId }]"
            @click="handleSwitchConversation(conv.id)"
          >
            <el-icon :size="14" :class="{ 'is-loading': chatStore.isConversationLoading(conv.id) }"><ChatDotRound /></el-icon>
            <span class="history-title">{{ conv.title }}</span>
            <el-button
              text
              circle
              class="history-delete"
              @click.stop="chatStore.removeConversation(conv.id)"
            >
              <el-icon :size="12"><Delete /></el-icon>
            </el-button>
          </div>
          <div
            v-if="chatStore.conversations.length > visibleCount"
            class="history-more"
            @click="visibleCount += 10"
          >
            加载更多
          </div>
          <div v-if="!chatStore.conversations.length" class="history-empty">
            暂无对话记录
          </div>
        </div>
      </div>
    </aside>

    <!-- 右侧主区域 -->
    <main class="main-area">
      <header class="main-header">
        <div class="header-title">
          <!-- 移动端汉堡菜单 -->
          <el-button
            v-if="isMobile"
            text
            circle
            class="hamburger"
            @click="mobileSidebarOpen = true"
          >
            <el-icon :size="18"><Menu /></el-icon>
          </el-button>
          <el-icon v-else :size="18"><ChatDotRound /></el-icon>
          <span class="title-text">{{ currentConversationTitle }}</span>
        </div>
        <div class="header-actions">
          <el-button
            text
            class="admin-entry-btn"
            @click="$router.push('/admin')"
          >
            <el-icon :size="14"><Setting /></el-icon>
            <span class="action-label">管理后台</span>
          </el-button>
          <el-dropdown trigger="click" @command="handleUserCommand">
            <span class="user-dropdown">
              <el-icon :size="16"><User /></el-icon>
              <span class="user-name">{{ currentUser.real_name }}</span>
              <el-icon :size="12"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="password">
                  <el-icon><Lock /></el-icon>修改密码
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <div class="chat-body">
        <MessageList @quick="handleQuickQuestion" @rollback="handleRollbackFill" />
      </div>

      <div class="chat-footer">
        <ChatInput ref="chatInputRef" />
        <div class="footer-tip">AI 提供的价格信息仅供采销参考，请以实际报价为准。</div>
      </div>
    </main>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="passwordDialog" title="修改密码" width="400px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="原密码">
          <el-input v-model="passwordForm.oldPassword" type="password" placeholder="请输入原密码" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.newPassword" type="password" placeholder="请输入新密码（至少6位）" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="passwordForm.confirmPassword" type="password" placeholder="再次输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialog = false">取消</el-button>
        <el-button type="primary" :loading="passwordLoading" @click="submitChangePassword">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from "vue"
import { useRouter } from "vue-router"
import { Delete, Plus, ChatDotRound, Fold, Expand, User, ArrowDown, Lock, SwitchButton, Setting, Menu, Close } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { useChatStore } from "../stores/chat"
import MessageList from "../components/chat/MessageList.vue"
import ChatInput from "../components/chat/ChatInput.vue"
import request from "../api/request"

const router = useRouter()
const chatStore = useChatStore()
const chatInputRef = ref()
const sidebarCollapsed = ref(false)

// 侧栏最近记录：默认展示 10 条，点击加载更多每次 +10
const visibleCount = ref(10)
const visibleConversations = computed(() =>
  chatStore.conversations.slice(0, visibleCount.value)
)

// 移动端断点 + 抽屉状态
const isMobile = ref(window.innerWidth <= 768)
const mobileSidebarOpen = ref(false)
function onResize() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) mobileSidebarOpen.value = false
}
window.addEventListener("resize", onResize)
onUnmounted(() => window.removeEventListener("resize", onResize))

function handleSwitchConversation(id: string) {
  chatStore.switchConversation(id)
  if (isMobile.value) mobileSidebarOpen.value = false
}

const currentUser = reactive(
  JSON.parse(localStorage.getItem("user") || '{"real_name":"用户","username":""}')
)

const currentConversationTitle = computed(() => {
  const conv = chatStore.conversations.find(c => c.id === chatStore.conversationId)
  return conv?.title || "新对话"
})

onMounted(() => {
  chatStore.loadConversations()
  chatStore.loadModels()
})

function handleClear() {
  chatStore.newConversation()
  if (isMobile.value) mobileSidebarOpen.value = false
}

function handleUserCommand(command: string) {
  if (command === "logout") {
    chatStore.reset()
    localStorage.removeItem("token")
    localStorage.removeItem("refresh_token")
    localStorage.removeItem("user")
    router.push("/login")
  } else if (command === "password") {
    handleChangePassword()
  }
}

async function handleChangePassword() {
  passwordDialog.value = true
}

const passwordDialog = ref(false)
const passwordForm = reactive({ oldPassword: "", newPassword: "", confirmPassword: "" })
const passwordLoading = ref(false)

async function submitChangePassword() {
  if (!passwordForm.oldPassword) {
    ElMessage.warning("请输入原密码")
    return
  }
  if (passwordForm.newPassword.length < 6) {
    ElMessage.warning("新密码至少6位")
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.warning("两次输入的密码不一致")
    return
  }
  passwordLoading.value = true
  try {
    await request.post("/auth/change-password", {
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword,
    })
    ElMessage.success("密码修改成功，请重新登录")
    passwordDialog.value = false
    // 清除登录状态，跳转到登录页
    chatStore.reset()
    localStorage.removeItem("token")
    localStorage.removeItem("refresh_token")
    localStorage.removeItem("user")
    router.push("/login")
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "修改失败")
  } finally {
    passwordLoading.value = false
  }
}

function handleQuickQuestion(q: string) {
  if (chatInputRef.value?.sendFromOutside) {
    chatInputRef.value.sendFromOutside(q)
  }
}

/** 回滚后把被删消息内容回填到输入框（不自动发送，便于用户修改后再发） */
function handleRollbackFill(content: string) {
  if (chatInputRef.value?.fillInput) {
    chatInputRef.value.fillInput(content)
  }
}
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: 100%;
  overflow: hidden;
  background: #f7f8fa;
}

/* ===== Sidebar ===== */
.sidebar {
  width: 240px;
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.25s ease;
  overflow: hidden;
}

.sidebar.collapsed {
  width: 60px;
}

.sidebar-header {
  padding: 16px 12px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}

.sidebar.collapsed .sidebar-header {
  justify-content: center;
}

/* 折叠状态：hover 侧边栏显示展开按钮 */
.logo-collapsed {
  width: 32px;
  height: 32px;
  position: relative;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-img-collapsed {
  width: 28px;
  height: 28px;
  transition: opacity 0.2s;
}

.expand-icon {
  position: absolute;
  inset: 0;
  margin: auto;
  color: #409eff;
  opacity: 0;
  transition: opacity 0.2s;
}

.sidebar.collapsed:hover .logo-img-collapsed {
  opacity: 0;
}

.sidebar.collapsed:hover .expand-icon {
  opacity: 1;
}

/* 展开状态 */
.logo-img-static {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.logo-text {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  flex: 1;
}

.collapse-btn {
  color: #909399;
}

.collapse-btn:hover {
  color: #409eff;
}

.sidebar-action {
  padding: 0 12px 16px;
  display: flex;
  justify-content: center;
}

.new-chat-btn {
  width: 100%;
  height: 38px;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
}

.sidebar-history {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px;
}

.history-label {
  font-size: 11px;
  color: #a8abb2;
  padding: 8px 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
  overflow: hidden;
}

.history-item:hover {
  background: #f5f7fa;
}

.history-item.active {
  background: #ecf5ff;
  color: #409eff;
}

.history-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-delete {
  opacity: 0;
  transition: opacity 0.2s;
  width: 20px;
  height: 20px;
  color: #c0c4cc;
}

.history-item:hover .history-delete {
  opacity: 1;
}

.history-delete:hover {
  color: #f56c6c;
}

.history-empty {
  font-size: 12px;
  color: #c0c4cc;
  text-align: center;
  padding: 20px 0;
}

.history-more {
  font-size: 12px;
  color: #909399;
  text-align: center;
  padding: 10px 0;
  cursor: pointer;
  user-select: none;
  transition: color 0.2s;
}

.history-more:hover {
  color: #409eff;
}

/* ===== Main Area ===== */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 500;
  color: #303133;
}

.header-btn {
  color: #909399;
}

.header-btn:hover {
  color: #f56c6c;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 6px;
  transition: background 0.2s;
  font-size: 13px;
  color: #606266;
}

.admin-entry-btn {
  font-size: 13px;
  color: #606266;
  margin-right: 8px;
}

.admin-entry-btn:hover {
  color: #409eff;
}

.user-dropdown:hover {
  background: #f5f7fa;
}

.user-name {
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 24px;
}

.chat-footer {
  padding: 12px 12px 5px;
  background: #fff;
  border-top: 1px solid #f0f0f0;
}

.footer-tip {
  text-align: center;
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 10px;
}

/* ===== Mobile ===== */
.mobile-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 998;
  animation: fade-in 0.2s ease;
}

.hamburger {
  margin-right: 4px;
  color: #606266;
}

.title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@media (max-width: 768px) {
  /* 侧栏在移动端变为绝对定位的抽屉 */
  .sidebar {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    width: 80vw;
    max-width: 320px;
    z-index: 999;
    box-shadow: 2px 0 16px rgba(0, 0, 0, 0.12);
    transform: translateX(-100%);
    transition: transform 0.25s ease;
  }
  .sidebar.mobile-open {
    transform: translateX(0);
  }
  .sidebar.mobile-hidden {
    transform: translateX(-100%);
  }

  .main-header {
    padding: 10px 12px;
  }

  .header-title {
    font-size: 14px;
    flex: 1;
    min-width: 0;
  }

  .admin-entry-btn .action-label {
    display: none;
  }

  .admin-entry-btn {
    margin-right: 0;
    padding: 6px;
  }

  .user-name {
    max-width: 60px;
    font-size: 12px;
  }

  .chat-body {
    padding: 12px;
  }

  .chat-footer {
    padding: 8px 8px 12px;
    padding-bottom: calc(12px + var(--safe-bottom));
  }

  .footer-tip {
    font-size: 10px;
    margin-top: 6px;
  }
}
</style>
