<template>
  <div class="admin-layout">
    <aside class="admin-sidebar">
      <div class="admin-logo">
        <img src="/favicon.svg" alt="logo" class="admin-logo-img" />
        <span>管理后台</span>
      </div>
      <el-menu :default-active="activeRoute" router class="admin-menu">
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
        <el-menu-item index="/admin/users">
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
    <main class="admin-main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useRoute } from "vue-router"
import { DataAnalysis, Goods, ChatDotRound, User, Back } from "@element-plus/icons-vue"

const route = useRoute()
const activeRoute = computed(() => route.path)
</script>

<style scoped>
.admin-layout {
  display: flex;
  height: 100%;
  overflow: hidden;
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
</style>
