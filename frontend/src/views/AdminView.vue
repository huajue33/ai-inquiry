<template>
  <div class="admin-layout">
    <!-- 移动端遮罩 -->
    <div
      v-if="isMobile && drawerOpen"
      class="admin-mask"
      @click="drawerOpen = false"
    ></div>

    <aside
      class="admin-sidebar"
      :class="{ 'mobile-open': isMobile && drawerOpen, 'mobile-hidden': isMobile && !drawerOpen }"
    >
      <div class="admin-logo">
        <img src="/favicon.svg" alt="logo" class="admin-logo-img" />
        <span>管理后台</span>
        <el-button
          v-if="isMobile"
          text
          circle
          class="close-btn"
          @click="drawerOpen = false"
        >
          <el-icon :size="16"><Close /></el-icon>
        </el-button>
      </div>
      <el-menu :default-active="activeRoute" router class="admin-menu" @select="onMenuSelect">
        <el-menu-item index="/admin">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据概览</span>
        </el-menu-item>
        <el-menu-item index="/admin/products">
          <el-icon><Goods /></el-icon>
          <span>商品管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/conversations">
          <el-icon><ChatDotRound /></el-icon>
          <span>对话记录</span>
        </el-menu-item>
        <el-menu-item v-if="canManageUsers" index="/admin/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
      </el-menu>
      <div class="admin-back">
        <el-button text @click="$router.push('/')">
          <el-icon><Back /></el-icon>
          返回对话
        </el-button>
      </div>
    </aside>

    <!-- 移动端顶部 bar -->
    <header v-if="isMobile" class="mobile-topbar">
      <el-button text circle @click="drawerOpen = true">
        <el-icon :size="20"><Menu /></el-icon>
      </el-button>
      <span class="topbar-title">{{ pageTitle }}</span>
      <span class="topbar-spacer"></span>
    </header>

    <main class="admin-main" :class="{ 'with-topbar': isMobile }">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onUnmounted } from "vue"
import { useRoute } from "vue-router"
import { DataAnalysis, Goods, ChatDotRound, User, Back, Menu, Close } from "@element-plus/icons-vue"

const route = useRoute()
const activeRoute = computed(() => route.path)

const currentUser = JSON.parse(localStorage.getItem("user") || '{"role":""}')
const canManageUsers = computed(
  () => currentUser.role === "admin" || currentUser.role === "manager"
)

const isMobile = ref(window.innerWidth <= 768)
const drawerOpen = ref(false)

function onResize() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) drawerOpen.value = false
}
window.addEventListener("resize", onResize)
onUnmounted(() => window.removeEventListener("resize", onResize))

function onMenuSelect() {
  if (isMobile.value) drawerOpen.value = false
}

const pageTitle = computed(() => {
  const map: Record<string, string> = {
    "/admin": "数据概览",
    "/admin/products": "商品管理",
    "/admin/conversations": "对话记录",
    "/admin/users": "用户管理",
  }
  return map[route.path] || "管理后台"
})
</script>

<style scoped>
.admin-layout {
  display: flex;
  height: 100%;
  overflow: hidden;
  position: relative;
}

.admin-sidebar {
  width: 200px;
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.admin-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.admin-logo-img {
  width: 28px;
  height: 28px;
  border-radius: 6px;
}

.close-btn {
  margin-left: auto;
  color: #909399;
}

.admin-menu {
  flex: 1;
  border-right: none;
}

.admin-back {
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
}

.admin-main {
  flex: 1;
  overflow-y: auto;
  background: #f7f8fa;
}

.admin-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 998;
  animation: fade-in 0.2s ease;
}

@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.mobile-topbar {
  display: none;
  align-items: center;
  height: 48px;
  padding: 0 8px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
}

.topbar-title {
  flex: 1;
  text-align: center;
  font-size: 15px;
  font-weight: 500;
  color: #303133;
}

.topbar-spacer {
  width: 40px;
}

@media (max-width: 768px) {
  .admin-sidebar {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    width: 78vw;
    max-width: 280px;
    z-index: 999;
    box-shadow: 2px 0 16px rgba(0, 0, 0, 0.12);
    transform: translateX(-100%);
    transition: transform 0.25s ease;
  }
  .admin-sidebar.mobile-open {
    transform: translateX(0);
  }
  .admin-sidebar.mobile-hidden {
    transform: translateX(-100%);
  }

  .mobile-topbar {
    display: flex;
  }

  .admin-main.with-topbar {
    padding-top: 48px;
  }
}
</style>
