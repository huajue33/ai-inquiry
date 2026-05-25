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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { User, Lock, WarningFilled } from "@element-plus/icons-vue"
import request from "../api/request"

const router = useRouter()
const username = ref("")
const password = ref("")
const loading = ref(false)
const errorMsg = ref("")

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
