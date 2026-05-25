<template>
  <div class="admin-page">
    <h2>{{ isAdmin ? "用户管理" : "采购员数据权限" }}</h2>
    <div class="toolbar">
      <el-button
        v-if="isAdmin"
        type="primary"
        size="small"
        @click="showCreateUser = true"
      >
        <el-icon><Plus /></el-icon> 新建用户
      </el-button>
      <el-tag v-if="!isAdmin" type="info" size="small">
        主管视图：仅可调整采购员的数据权限
      </el-tag>
    </div>
    <el-table :data="users" stripe style="width: 100%">
      <el-table-column prop="id" label="ID" min-width="60" />
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="real_name" label="姓名" min-width="100" />
      <el-table-column v-if="isAdmin" prop="role" label="角色" min-width="100">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'manager' ? 'warning' : 'info'" size="small">
            {{ row.role === 'admin' ? '管理员' : row.role === 'manager' ? '主管' : '采购员' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="isAdmin" prop="is_active" label="状态" min-width="80">
        <template #default="{ row }">
          <el-tooltip
            v-if="row.id === currentUserId"
            content="不能修改自己的账号状态"
            placement="top"
          >
            <el-switch :model-value="!!row.is_active" disabled />
          </el-tooltip>
          <el-switch
            v-else
            :model-value="!!row.is_active"
            @change="(v: boolean) => toggleUser(row.id, v)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="170" />
      <el-table-column label="操作" min-width="200">
        <template #default="{ row }">
          <el-button
            v-if="isAdmin && row.id !== currentUserId"
            text
            size="small"
            @click="resetPassword(row.id)"
          >重置密码</el-button>
          <el-button
            v-if="row.role === 'buyer'"
            text
            size="small"
            type="primary"
            @click="openPermissions(row)"
          >数据权限</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建用户（仅 admin） -->
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

    <!-- 数据权限 -->
    <el-drawer
      v-model="showPermDialog"
      :title="`数据权限 - ${permTarget?.real_name}`"
      size="480px"
      direction="rtl"
    >
      <div class="perm-drawer-body">
        <p class="perm-tip">
          勾选后，该用户只能在 AI 对话中查询被授权的<strong>二级分类</strong>下的产品。<br />
          管理员和主管不受此限制。
        </p>
        <div class="perm-toolbar">
          <el-button size="small" @click="selectAllPerms">全选</el-button>
          <el-button size="small" @click="clearAllPerms">清空</el-button>
          <el-button size="small" @click="toggleExpand">
            {{ allExpanded ? "收起全部" : "展开全部" }}
          </el-button>
          <span class="perm-counter">已选 {{ selectedCategoryIds.length }} 个</span>
        </div>
        <el-tree
          ref="permTreeRef"
          :data="permTreeData"
          show-checkbox
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :default-checked-keys="selectedCategoryIds"
          :default-expand-all="false"
          @check="onPermCheck"
          class="perm-tree"
        />
      </div>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="showPermDialog = false">取消</el-button>
          <el-button type="primary" @click="savePermissions">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted } from "vue"
import { Plus } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import request from "../../api/request"

interface UserRow {
  id: number
  username: string
  real_name: string
  role: string
  is_active: number
  created_at: string
}

interface CategoryItem {
  id: number
  name: string
  parent_id: number | null
  level: number
}

const users = ref<UserRow[]>([])
const showCreateUser = ref(false)
const newUser = reactive({ username: "", real_name: "", password: "", role: "buyer" })

const currentUser = JSON.parse(localStorage.getItem("user") || '{"role":"","user_id":0}')
const isAdmin = computed(() => currentUser.role === "admin")
const currentUserId = computed<number>(() => currentUser.user_id || 0)

// ===== 权限弹窗 =====
const showPermDialog = ref(false)
const permTarget = ref<UserRow | null>(null)
const categories = ref<CategoryItem[]>([])
const selectedCategoryIds = ref<number[]>([])
const permTreeRef = ref<any>(null)
const allExpanded = ref(false)

interface PermTreeNode {
  id: number
  name: string
  children?: PermTreeNode[]
  disabled?: boolean
}

// 树结构：一级 → 二级（只到二级，因为权限粒度就是二级）
const permTreeData = computed<PermTreeNode[]>(() => {
  return categories.value
    .filter((c) => c.level === 1)
    .map((top) => ({
      id: -top.id, // 负数避免与二级 id 冲突；保存时只取正数
      name: top.name,
      children: categories.value
        .filter((c) => c.level === 2 && c.parent_id === top.id)
        .map((sub) => ({ id: sub.id, name: sub.name })),
    }))
})

// 所有二级分类 id 列表（用于全选）
const allSecondLevelIds = computed(() =>
  categories.value.filter((c) => c.level === 2).map((c) => c.id)
)

function onPermCheck() {
  if (!permTreeRef.value) return
  // el-tree 勾选可能包含一级（id<0）和二级（id>0），只保留二级
  const checked: number[] = permTreeRef.value.getCheckedKeys(false)
  selectedCategoryIds.value = checked.filter((id) => id > 0)
}

function selectAllPerms() {
  selectedCategoryIds.value = [...allSecondLevelIds.value]
  if (permTreeRef.value) {
    permTreeRef.value.setCheckedKeys(allSecondLevelIds.value)
  }
}

function clearAllPerms() {
  selectedCategoryIds.value = []
  if (permTreeRef.value) {
    permTreeRef.value.setCheckedKeys([])
  }
}

function expandAll() {
  if (!permTreeRef.value) return
  // el-tree 没有 expandAll API，用 store 节点遍历
  const nodes = permTreeRef.value.store?.nodesMap
  if (nodes) {
    Object.values(nodes).forEach((n: any) => (n.expanded = true))
  }
  allExpanded.value = true
}

function collapseAll() {
  if (!permTreeRef.value) return
  const nodes = permTreeRef.value.store?.nodesMap
  if (nodes) {
    Object.values(nodes).forEach((n: any) => (n.expanded = false))
  }
  allExpanded.value = false
}

function toggleExpand() {
  if (allExpanded.value) collapseAll()
  else expandAll()
}

onMounted(() => {
  loadUsers()
  loadCategories()
})

async function loadUsers() {
  try {
    const res: any = await request.get("/admin/users")
    users.value = res.users
  } catch { /* ignore */ }
}

async function loadCategories() {
  try {
    const res: any = await request.get("/admin/categories")
    categories.value = res.categories
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

async function openPermissions(row: UserRow) {
  permTarget.value = row
  selectedCategoryIds.value = []
  showPermDialog.value = true
  try {
    const res: any = await request.get(`/admin/users/${row.id}/permissions`)
    selectedCategoryIds.value = res.category_ids || []
    // 等弹窗渲染完成后再设置勾选
    await nextTick()
    if (permTreeRef.value) {
      permTreeRef.value.setCheckedKeys(selectedCategoryIds.value)
    }
  } catch { /* ignore */ }
}

async function savePermissions() {
  if (!permTarget.value) return
  try {
    await request.put(`/admin/users/${permTarget.value.id}/permissions`, {
      user_id: permTarget.value.id,
      category_ids: selectedCategoryIds.value,
    })
    ElMessage.success(`已保存（${selectedCategoryIds.value.length} 个分类）`)
    showPermDialog.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败")
  }
}
</script>

<style scoped>
.admin-page { padding: 24px; }
.admin-page h2 { font-size: 18px; font-weight: 600; color: #303133; margin: 0 0 20px; }
.toolbar { margin-bottom: 16px; display: flex; gap: 12px; align-items: center; }

.perm-drawer-body {
  padding: 0 4px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.perm-tip {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  color: #606266;
  margin: 0 0 12px;
  line-height: 1.7;
}

.perm-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #ebeef5;
  flex-wrap: wrap;
}

.perm-counter {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}

.perm-tree {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.perm-tree :deep(.el-tree-node__content) {
  height: 32px;
}

.perm-tree :deep(.el-tree-node__label) {
  font-size: 13px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
