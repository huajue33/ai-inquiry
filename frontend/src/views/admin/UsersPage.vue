<template>
  <div class="admin-page">
    <h2>用户管理</h2>
    <div class="toolbar">
      <el-button type="primary" size="small" @click="showCreateUser = true">
        <el-icon><Plus /></el-icon> 新建用户
      </el-button>
    </div>
    <el-table :data="users" stripe style="width: 100%">
      <el-table-column prop="id" label="ID" min-width="60" />
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="real_name" label="姓名" min-width="100" />
      <el-table-column prop="role" label="角色" min-width="100">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'manager' ? 'warning' : 'info'" size="small">
            {{ row.role === 'admin' ? '管理员' : row.role === 'manager' ? '主管' : '采购员' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" min-width="80">
        <template #default="{ row }">
          <el-switch :model-value="!!row.is_active" @change="(v: boolean) => toggleUser(row.id, v)" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="170" />
      <el-table-column label="操作" min-width="100">
        <template #default="{ row }">
          <el-button text size="small" @click="resetPassword(row.id)">重置密码</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showCreateUser" title="新建用户" width="420px">
      <el-form label-width="70px">
        <el-form-item label="用户名">
          <el-input v-model="newUser.username" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="newUser.real_name" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="newUser.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="newUser.role">
            <el-option label="采购员" value="buyer" />
            <el-option label="主管" value="manager" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateUser = false">取消</el-button>
        <el-button type="primary" @click="createUser">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue"
import { Plus } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import request from "../../api/request"

const users = ref<any[]>([])
const showCreateUser = ref(false)
const newUser = reactive({ username: "", real_name: "", password: "", role: "buyer" })

onMounted(() => { loadUsers() })

async function loadUsers() {
  try {
    const res: any = await request.get("/admin/users")
    users.value = res.users
  } catch { /* ignore */ }
}

async function createUser() {
  if (!newUser.username || !newUser.password || !newUser.real_name) {
    ElMessage.warning("请填写完整信息")
    return
  }
  try {
    await request.post("/admin/users", newUser)
    ElMessage.success("创建成功")
    showCreateUser.value = false
    newUser.username = ""
    newUser.real_name = ""
    newUser.password = ""
    newUser.role = "buyer"
    loadUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "创建失败")
  }
}

async function toggleUser(userId: number, active: boolean) {
  try {
    await request.put(`/admin/users/${userId}`, { is_active: active ? 1 : 0 })
    loadUsers()
  } catch { /* ignore */ }
}

async function resetPassword(userId: number) {
  try {
    const { value } = await ElMessageBox.prompt("请输入新密码", "重置密码", {
      inputType: "password",
      inputValidator: (v) => (!v || v.length < 6) ? "密码至少6位" : true,
    })
    if (value) {
      await request.put(`/admin/users/${userId}`, { password: value })
      ElMessage.success("密码已重置")
    }
  } catch { /* cancelled */ }
}
</script>

<style scoped>
.admin-page { padding: 24px; }
.admin-page h2 { font-size: 18px; font-weight: 600; color: #303133; margin: 0 0 20px; }
.toolbar { margin-bottom: 16px; display: flex; gap: 12px; }
</style>
