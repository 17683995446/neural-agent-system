import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Home', component: () => import('../views/Home.vue') },
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue') },
  { path: '/register', name: 'Register', component: () => import('../views/Register.vue') },
  { path: '/dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { requiresAuth: true } },
  { path: '/diagnosis', name: 'Diagnosis', component: () => import('../views/Diagnosis.vue'), meta: { requiresAuth: true } },
  { path: '/practice', name: 'Practice', component: () => import('../views/Practice.vue'), meta: { requiresAuth: true } },
  { path: '/questions', name: 'QuestionBank', component: () => import('../views/QuestionBank.vue'), meta: { requiresAuth: true } },
  { path: '/exam', name: 'ExamList', component: () => import('../views/ExamList.vue'), meta: { requiresAuth: true } },
  { path: '/exam/:id', name: 'ExamTake', component: () => import('../views/ExamTake.vue'), meta: { requiresAuth: true } },
  { path: '/exam/result/:id', name: 'ExamResult', component: () => import('../views/ExamResult.vue'), meta: { requiresAuth: true } },
  { path: '/courses', name: 'CourseList', component: () => import('../views/CourseList.vue'), meta: { requiresAuth: true } },
  { path: '/course/:id', name: 'CourseDetail', component: () => import('../views/CourseDetail.vue'), meta: { requiresAuth: true } },
  { path: '/wrong-book', name: 'WrongBook', component: () => import('../views/WrongBook.vue'), meta: { requiresAuth: true } },
  { path: '/qa', name: 'QA', component: () => import('../views/QA.vue'), meta: { requiresAuth: true } },
  { path: '/profile', name: 'Profile', component: () => import('../views/Profile.vue'), meta: { requiresAuth: true } },
  { path: '/orders', name: 'Orders', component: () => import('../views/Orders.vue'), meta: { requiresAuth: true } },
  { path: '/study-plan', name: 'StudyPlan', component: () => import('../views/StudyPlan.vue'), meta: { requiresAuth: true } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth) {
    const token = localStorage.getItem('token')
    if (!token) {
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
  }
  next()
})

export default router
