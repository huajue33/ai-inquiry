import { createRouter, createWebHistory } from "vue-router"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "Chat",
      component: () => import("../views/ChatView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/admin",
      component: () => import("../views/AdminView.vue"),
      meta: { requiresAuth: true },
      children: [
        {
          path: "",
          name: "AdminDashboard",
          component: () => import("../views/admin/DashboardPage.vue"),
        },
        {
          path: "products",
          name: "AdminProducts",
          component: () => import("../views/admin/ProductsPage.vue"),
        },
        {
          path: "conversations",
          name: "AdminConversations",
          component: () => import("../views/admin/ConversationsPage.vue"),
        },
        {
          path: "users",
          name: "AdminUsers",
          component: () => import("../views/admin/UsersPage.vue"),
        },
      ],
    },
    {
      path: "/login",
      name: "Login",
      component: () => import("../views/LoginView.vue"),
    },
  ],
})

/** 路由守卫：检查登录态和角色权限，未登录跳转/login，已登录访问/login则重定向到/ */
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem("token")
  if (to.meta.requiresAuth && !token) {
    next("/login")
    return
  }
  if (to.path === "/login" && token) {
    next("/")
    return
  }
  // /admin/users 需要 admin 或 manager；其余 /admin/* 任意登录用户可访问
  if (to.path.startsWith("/admin/users")) {
    try {
      const user = JSON.parse(localStorage.getItem("user") || "{}")
      if (user.role !== "admin" && user.role !== "manager") {
        next("/admin")
        return
      }
    } catch {
      next("/admin")
      return
    }
  }
  next()
})

export default router
