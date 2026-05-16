<template>
  <div class="page-container dashboard-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <div class="welcome-bar">
          <h2>欢迎回来，{{ userStore.user?.nickname || '学员' }}</h2>
          <p>坚持学习，CPA通关就在前方！</p>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="stats-row">
      <el-col :xs="12" :sm="6" v-for="s in statCards" :key="s.label">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" :style="{background: s.color}">{{ s.icon }}</div>
          <div class="stat-info">
            <div class="stat-value">{{ s.value }}</div>
            <div class="stat-label">{{ s.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><span>科目掌握度</span></template>
          <div ref="pieRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><span>学习趋势</span></template>
          <div ref="lineRef" class="chart-box"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top:20px">
      <el-col :xs="24" :sm="12">
        <el-card shadow="hover">
          <template #header><span>📋 AI推荐练习</span></template>
          <div v-if="recommendLoading" style="text-align:center;padding:20px"><el-icon class="is-loading"><Loading /></el-icon> 加载中...</div>
          <div v-else-if="recommended.length === 0" class="empty-tip">暂无推荐，去<a @click="$router.push('/diagnosis')">AI诊断</a>生成学习画像</div>
          <div v-else>
            <div v-for="q in recommended" :key="q.id" class="rec-item" @click="$router.push('/practice')">
              <SubjectBadge :subject="q.subject" />
              <span class="rec-title">{{ q.content?.substring(0, 40) }}...</span>
              <el-tag size="small" :type="difficultyType(q.difficulty)">{{ q.difficulty }}</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12">
        <el-card shadow="hover">
          <template #header><span>📅 学习计划</span></template>
          <div v-if="planLoading" style="text-align:center;padding:20px"><el-icon class="is-loading"><Loading /></el-icon> 加载中...</div>
          <div v-else-if="!studyPlan" class="empty-tip">暂无学习计划，<a @click="$router.push('/study-plan')">生成学习计划</a></div>
          <div v-else>
            <el-timeline>
              <el-timeline-item v-for="(task, i) in (studyPlan.today_tasks || []).slice(0, 5)" :key="i" :timestamp="task.time" placement="top">
                {{ task.content }}
              </el-timeline-item>
            </el-timeline>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useUserStore } from '../stores/user'
import { aiApi } from '../api/ai'
import SubjectBadge from '../components/SubjectBadge.vue'

const userStore = useUserStore()
const pieRef = ref()
const lineRef = ref()
const recommended = ref([])
const recommendLoading = ref(false)
const studyPlan = ref(null)
const planLoading = ref(false)

const statCards = ref([
  { icon: '📝', label: '已做题目', value: '0', color: '#e6f7ff' },
  { icon: '✅', label: '正确率', value: '0%', color: '#f6ffed' },
  { icon: '📖', label: '学习时长', value: '0h', color: '#fff7e6' },
  { icon: '🔥', label: '连续天数', value: '0', color: '#fff1f0' }
])

const difficultyType = (d) => {
  if (d === 'easy' || d === 1) return 'success'
  if (d === 'medium' || d === 2) return 'warning'
  return 'danger'
}

onMounted(async () => {
  await userStore.fetchProfile()
  const user = userStore.user
  if (user) {
    statCards.value[0].value = String(user.total_questions || 0)
    statCards.value[1].value = (user.accuracy ? (user.accuracy * 100).toFixed(1) + '%' : '0%')
    statCards.value[2].value = (user.study_hours || 0) + 'h'
    statCards.value[3].value = String(user.streak_days || 0)
  }
  recommendLoading.value = true
  planLoading.value = true
  try { const res = await aiApi.recommend({ count: 5 }); recommended.value = res.data } catch {} finally { recommendLoading.value = false }
  try { const res = await aiApi.studyPlan(); studyPlan.value = res.data } catch {} finally { planLoading.value = false }
  await nextTick()
  initPieChart()
  initLineChart()
})

let pieChart = null
let lineChart = null

const initPieChart = () => {
  if (!pieRef.value) return
  pieChart = echarts.init(pieRef.value)
  pieChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '70%'], label: { show: true, formatter: '{b}\n{d}%' },
      data: [
        { value: 35, name: '会计', itemStyle: { color: '#1890ff' } },
        { value: 25, name: '审计', itemStyle: { color: '#722ed1' } },
        { value: 20, name: '财管', itemStyle: { color: '#13c2c2' } },
        { value: 10, name: '经济法', itemStyle: { color: '#eb2f96' } },
        { value: 7, name: '税法', itemStyle: { color: '#fa8c16' } },
        { value: 3, name: '战略', itemStyle: { color: '#52c41a' } }
      ]
    }]
  })
}

const initLineChart = () => {
  if (!lineRef.value) return
  lineChart = echarts.init(lineRef.value)
  const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  lineChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: days },
    yAxis: { type: 'value', name: '题数' },
    series: [
      { name: '做题数', type: 'line', smooth: true, data: [30, 45, 28, 50, 42, 60, 35], areaStyle: { opacity: 0.1 }, itemStyle: { color: '#1890ff' } },
      { name: '正确数', type: 'line', smooth: true, data: [22, 36, 20, 42, 34, 50, 28], areaStyle: { opacity: 0.1 }, itemStyle: { color: '#52c41a' } }
    ]
  })
}

const handleResize = () => { pieChart?.resize(); lineChart?.resize() }
window.addEventListener('resize', handleResize)

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  pieChart?.dispose()
  lineChart?.dispose()
})
</script>

<style scoped>
.dashboard-page { padding-bottom: 40px; }
.welcome-bar { background: linear-gradient(135deg, #1890ff, #096dd9); color: #fff; border-radius: 12px; padding: 24px 32px; margin-bottom: 20px; }
.welcome-bar h2 { font-size: 22px; margin-bottom: 4px; }
.welcome-bar p { opacity: 0.85; font-size: 14px; }
.stats-row { margin-bottom: 20px; }
.stat-card { display: flex; align-items: center; padding: 16px; }
.stat-card :deep(.el-card__body) { display: flex; align-items: center; gap: 12px; width: 100%; }
.stat-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 24px; flex-shrink: 0; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--cpa-text); }
.stat-label { font-size: 13px; color: var(--cpa-text-secondary); }
.chart-card :deep(.el-card__header) { font-size: 16px; font-weight: 600; }
.chart-box { height: 280px; }
.rec-item { display: flex; align-items: center; gap: 8px; padding: 10px 0; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
.rec-item:hover { background: #fafafa; }
.rec-title { flex: 1; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty-tip { text-align: center; padding: 20px; color: var(--cpa-text-secondary); }
.empty-tip a { color: var(--cpa-primary); cursor: pointer; }
</style>
