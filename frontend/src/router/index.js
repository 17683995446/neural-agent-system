import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/architecture' },
  { path: '/architecture', name: 'Architecture', component: () => import('../views/ArchitectureView.vue'), meta: { title: '架构图' } },
  { path: '/sequence', name: 'Sequence', component: () => import('../views/SequenceView.vue'), meta: { title: '时序图' } },
  { path: '/modules', name: 'Modules', component: () => import('../views/ModulesView.vue'), meta: { title: '模块原理' } },
  { path: '/flow', name: 'Flow', component: () => import('../views/FlowView.vue'), meta: { title: '流程图' } },
  { path: '/state', name: 'State', component: () => import('../views/StateView.vue'), meta: { title: '状态图' } },
  { path: '/dashboard', name: 'Dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '实时仪表盘' } },
]

export default createRouter({ history: createWebHistory(), routes })
