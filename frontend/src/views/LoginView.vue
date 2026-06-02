<template>
  <div class="login-page">
    <div class="login-left">
      <div class="login-brand">
        <img src="/favicon.svg" alt="logo" class="brand-logo" />
        <h1 class="brand-title">AI 询价助手</h1>
        <p class="brand-desc">智能采销价格查询平台</p>
      </div>
      <div class="login-features">
        <div class="feature-item">
          <div class="feature-dot"></div>
          <span>实时查询 10000+ 产品最新价格</span>
        </div>
        <div class="feature-item">
          <div class="feature-dot"></div>
          <span>AI 智能分析价格趋势与涨跌排行</span>
        </div>
        <div class="feature-item">
          <div class="feature-dot"></div>
          <span>多品牌、多品质横向比价对比</span>
        </div>
      </div>
    </div>
    <div class="login-right">
      <div class="login-form-wrapper">
        <h2>欢迎登录</h2>
        <p class="form-subtitle">请输入您的账号信息</p>
        <el-form @submit.prevent="handleLogin" class="login-form">
          <el-form-item>
            <el-input
              v-model="username"
              placeholder="用户名"
              size="large"
              :prefix-icon="User"
            />
          </el-form-item>
          <el-form-item>
            <el-input
              v-model="password"
              type="password"
              placeholder="密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>
          <div v-if="errorMsg" class="error-msg">
            <el-icon :size="14"><WarningFilled /></el-icon>
            {{ errorMsg }}
          </div>
          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            size="large"
            class="login-btn"
          >
            登录
          </el-button>
        </el-form>
        <div class="test-accounts">
          <div class="test-accounts-header">
            <el-icon :size="14"><InfoFilled /></el-icon>
            测试账号（点击自动填入）
          </div>
          <div
            class="test-account-row"
            v-for="acc in testAccounts"
            :key="acc.username"
            @click="fillAccount(acc.username, acc.password)"
          >
            <span :class="['test-account-tag', acc.role]">{{ acc.username }}</span>
            <span class="test-account-role">{{ acc.label }}</span>
            <span class="test-account-pwd">
              <el-icon :size="12"><Lock /></el-icon>
              {{ acc.password }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { User, Lock, WarningFilled, InfoFilled } from "@element-plus/icons-vue"
import request from "../api/request"

const router = useRouter()
const username = ref("")
const password = ref("")
const loading = ref(false)
const errorMsg = ref("")

const testAccounts = [
  { username: "admin", password: "123456", role: "admin", label: "管理员" },
  { username: "test", password: "123456", role: "manager", label: "主管" },
  { username: "test001", password: "123456", role: "buyer", label: "采购员" },
]

function fillAccount(user: string, pwd: string) {
  username.value = user
  password.value = pwd
  errorMsg.value = ""
}

async function handleLogin() {
  if (!username.value || !password.value) {
    errorMsg.value = "请输入用户名和密码"
    return
  }
  loading.value = true
  errorMsg.value = ""

  try {
    const res: any = await request.post("/auth/login", {
      username: username.value,
      password: password.value,
    })
    localStorage.setItem("token", res.access_token)
    localStorage.setItem("refresh_token", res.refresh_token)
    localStorage.setItem("user", JSON.stringify({
      user_id: res.user_id,
      username: res.username,
      real_name: res.real_name,
      role: res.role,
    }))
    router.push("/")
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || "登录失败，请检查用户名和密码"
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* Left panel */
.login-left {
  flex: 1;
  background: linear-gradient(135deg, #409eff 0%, #6366f1 100%);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 60px;
  color: #fff;
  position: relative;
  overflow: hidden;
  text-align: center;
}.login-left::before {
  content: "";
  position: absolute;
  top: -20%;
  right: -10%;
  width: 400px;
  height: 400px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
}

.login-left::after {
  content: "";
  position: absolute;
  bottom: -15%;
  left: -5%;
  width: 300px;
  height: 300px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.03);
}

.login-brand {
  position: relative;
  z-index: 1;
  margin-bottom: 48px;
}

.brand-logo {
  width: 80px;
  height: 80px;
  margin-bottom: 24px;
}

.brand-title {
  font-size: 36px;
  font-weight: 700;
  margin: 0 0 12px;
  letter-spacing: 1px;
}

.brand-desc {
  font-size: 18px;
  opacity: 0.8;
  margin: 0;
}

.login-features {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 18px;
  text-align: left;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  padding: 28px 32px;
  backdrop-filter: blur(4px);
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 15px;
  opacity: 0.95;
}

.feature-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
  flex-shrink: 0;
}

/* Right panel */
.login-right {
  width: 480px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  padding: 60px;
}

.login-form-wrapper {
  width: 100%;
  max-width: 340px;
}

.login-form-wrapper h2 {
  font-size: 24px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 8px;
}

.form-subtitle {
  font-size: 14px;
  color: #909399;
  margin: 0 0 32px;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  height: 44px;
}

.error-msg {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #f56c6c;
  font-size: 13px;
  margin-bottom: 12px;
}

.login-btn {
  width: 100%;
  height: 44px;
  border-radius: 10px;
  font-size: 15px;
  margin-top: 8px;
}

/* Test accounts */
.test-accounts {
  margin-top: 28px;
  padding: 16px 16px 12px;
  background: #f8f9fc;
  border-radius: 12px;
  border: 1px solid #ebeef5;
  transition: border-color 0.2s;
}

.test-accounts-header {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #909399;
  margin-bottom: 12px;
  font-size: 12px;
}

.test-account-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  margin-bottom: 4px;
}

.test-account-row:last-child {
  margin-bottom: 0;
}

.test-account-row:hover {
  background: #eef1f6;
  transform: translateX(2px);
}

.test-account-row:active {
  transform: translateX(2px) scale(0.99);
}

.test-account-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 10px;
  border-radius: 6px;
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  min-width: 60px;
  height: 24px;
  letter-spacing: 0.3px;
}

.test-account-tag.admin {
  background: #ecf5ff;
  color: #409eff;
}

.test-account-tag.manager {
  background: #fdf6ec;
  color: #e6a23c;
}

.test-account-tag.buyer {
  background: #f0f9eb;
  color: #67c23a;
}

.test-account-role {
  color: #606266;
  font-size: 12px;
  flex: 1;
}

.test-account-pwd {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: #c0c4cc;
  font-size: 11px;
  font-family: monospace;
  opacity: 0;
  transition: opacity 0.15s;
}

.test-account-row:hover .test-account-pwd {
  opacity: 1;
}

/* ===== Mobile ===== */
@media (max-width: 768px) {
  .login-page {
    flex-direction: column;
    background: linear-gradient(135deg, #409eff 0%, #6366f1 100%);
  }

  .login-left {
    flex: 0 0 auto;
    padding: 32px 24px 24px;
  }

  .login-left::before,
  .login-left::after {
    display: none;
  }

  .brand-logo {
    width: 56px;
    height: 56px;
    margin-bottom: 12px;
  }

  .brand-title {
    font-size: 24px;
    margin-bottom: 6px;
  }

  .brand-desc {
    font-size: 13px;
    margin-bottom: 0;
  }

  .login-brand {
    margin-bottom: 0;
  }

  .login-features {
    display: none;
  }

  .login-right {
    flex: 1;
    width: 100%;
    padding: 24px;
    border-radius: 24px 24px 0 0;
    background: #fff;
    margin-top: -8px;
  }

  .login-form-wrapper {
    max-width: 100%;
  }

  .login-form-wrapper h2 {
    font-size: 20px;
  }

  .form-subtitle {
    margin-bottom: 24px;
  }
}
</style>
