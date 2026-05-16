<template>
  <div id="app-wrapper">
    <el-header class="app-header" v-if="showHeader">
      <div class="header-inner">
        <div class="logo" @click="$router.push('/')">
          <span class="logo-icon">📚</span>
          <span class="logo-text">AI CPA 智能备考</span>
        </div>
        <el-menu :default-active="activeMenu" mode="horizontal" :ellipsis="false" class="nav-menu" router>
          <el-menu-item index="/dashboard">学习中心</el-menu-item>
          <el-menu-item index="/diagnosis">AI诊断</el-menu-item>
          <el-menu-item index="/practice">智能刷题</el-menu-item>
          <el-menu-item index="/questions">题库</el-menu-item>
          <el-menu-item index="/exam">机考模拟</el-menu-item>
          <el-menu-item index="/courses">课程</el-menu-item>
        </el-menu>
        <div class="header-right">
          <template v-if="userStore.isLoggedIn">
            <el-dropdown trigger="click" @command="handleDropdownCommand">
              <span class="user-dropdown">
                <el-avatar :size="28" class="user-avatar">{{ userStore.user?.nickname?.charAt(0) || '用' }}</el-avatar>
                <span class="user-name">{{ userStore.user?.nickname || '用户' }}</span>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="/profile">个人中心</el-dropdown-item>
                  <el-dropdown-item command="/wrong-book">错题本</el-dropdown-item>
                  <el-dropdown-item command="/qa">AI答疑</el-dropdown-item>
                  <el-dropdown-item command="/study-plan">学习计划</el-dropdown-item>
                  <el-dropdown-item command="/orders">我的订单</el-dropdown-item>
                  <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else>
            <el-button type="primary" @click="$router.push('/login')">登录</el-button>
            <el-button @click="$router.push('/register')">注册</el-button>
          </template>
        </div>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
    <el-footer class="app-footer" v-if="showHeader">
      <div class="footer-inner">
        <p>© 2026 AI CPA 智能备考平台 | 注册会计师考试智能辅导系统</p>
        <p>让AI助力您的CPA备考之旅</p>
      </div>
    </el-footer>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from './stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/practice')) return '/practice'
  if (path.startsWith('/questions')) return '/questions'
  if (path.startsWith('/exam')) return '/exam'
  if (path.startsWith('/courses') || path.startsWith('/course')) return '/courses'
  return path
})

const showHeader = computed(() => !['/login', '/register'].includes(route.path))

const handleDropdownCommand = (command) => {
  if (command === 'logout') {
    userStore.logout()
  } else {
    router.push(command)
  }
}
</script>
