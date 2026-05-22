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

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem("token")
  if (to.meta.requiresAuth && !token) {
    next("/login")
  } else if (to.path === "/login" && token) {
    next("/")
  } else {
    next()
  }
})

export default router
