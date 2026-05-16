<template>
  <div class="page-container study-plan-page">
    <h1 class="page-title">📅 AI 学习计划</h1>

    <div v-if="!plan && !loading" class="generate-box">
      <el-card shadow="hover">
        <h3>生成个性化学习计划</h3>
        <p>AI将根据您的诊断结果和学习目标，为您定制最优学习路径</p>
        <el-button type="primary" size="large" @click="generatePlan" :loading="generating">生成学习计划</el-button>
      </el-card>
    </div>

    <div v-if="loading" class="loading-box">
      <el-icon class="is-loading" :size="48"><Loading /></el-icon>
      <p>AI正在为您规划学习路径...</p>
    </div>

    <div v-if="plan && !loading" class="plan-content">
      <el-row :gutter="20">
        <el-col :xs="24" :sm="16">
          <el-card shadow="hover">
            <template #header>
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span>📋 学习时间线</span>
                <el-button size="small" @click="generatePlan" :loading="generating">重新生成</el-button>
              </div>
            </template>
            <el-timeline>
              <el-timeline-item v-for="(phase, i) in plan.phases || []" :key="i" :timestamp="phase.period" placement="top" type="primary">
                <h4>{{ phase.title }}</h4>
                <p>{{ phase.description }}</p>
                <div class="phase-tasks">
                  <div v-for="(task, j) in phase.tasks || []" :key="j" class="task-item">
                    <el-checkbox v-model="task.done" @change="toggleTask(task)">{{ task.content }}</el-checkbox>
                    <el-tag size="small" :type="task.subject ? 'primary' : 'info'">{{ task.subject || '综合' }}</el-tag>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-card shadow="hover" style="margin-bottom:16px">
            <template #header><span>📊 整体进度</span></template>
            <div ref="progressRef" class="chart-box"></div>
          </el-card>
          <el-card shadow="hover" style="margin-bottom:16px">
            <template #header><span>📋 今日任务</span></template>
            <div v-for="(task, i) in (plan.today_tasks || []).slice(0, 6)" :key="i" class="today-task">
              <el-checkbox v-model="task.done">{{ task.content }}</el-checkbox>
            </div>
            <div v-if="!plan.today_tasks?.length" class="empty-tip">今日暂无任务</div>
          </el-card>
          <el-card shadow="hover">
            <template #header><span>🎯 目标</span></template>
            <div class="goals">
              <p v-for="(g, i) in (plan.goals || [])" :key="i">• {{ g }}</p>
              <div v-if="!plan.goals?.length" class="empty-tip">暂无目标</div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { aiApi } from '../api/ai'

const loading = ref(false)
const generating = ref(false)
const plan = ref(null)
const progressRef = ref()

const generatePlan = async () => {
  generating.value = true
  try {
    const res = await aiApi.studyPlan({ regenerate: true })
    plan.value = res.data
    await nextTick()
    initProgressChart()
  } catch {} finally { generating.value = false }
}

const toggleTask = (task) => {}

let progressChart = null

const initProgressChart = () => {
  if (!progressRef.value) return
  if (progressChart) progressChart.dispose()
  progressChart = echarts.init(progressRef.value)
  const subjects = ['会计', '审计', '财管', '经济法', '税法', '战略']
  const mastery = plan.value?.subject_mastery || [65, 45, 55, 70, 40, 60]
  progressChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: subjects },
    yAxis: { type: 'value', max: 100, name: '掌握度%' },
    series: [{
      type: 'bar', data: mastery,
      itemStyle: { color: (p) => { const colors = ['#1890ff', '#722ed1', '#13c2c2', '#eb2f96', '#fa8c16', '#52c41a']; return colors[p.dataIndex] } }
    }]
  })
}

const handleResize = () => progressChart?.resize()
window.addEventListener('resize', handleResize)

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  progressChart?.dispose()
})

onMounted(async () => {
  loading.value = true
  try { const res = await aiApi.studyPlan(); plan.value = res.data; await nextTick(); initProgressChart() } catch {} finally { loading.value = false }
})
</script>

<style scoped>
.generate-box { text-align: center; padding: 60px 0; }
.generate-box h3 { font-size: 20px; margin-bottom: 12px; }
.generate-box p { color: var(--cpa-text-secondary); margin-bottom: 24px; }
.loading-box { text-align: center; padding: 60px 0; }
.loading-box p { margin-top: 12px; color: var(--cpa-text-secondary); }
.chart-box { height: 220px; }
.phase-tasks { margin-top: 8px; }
.task-item { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.today-task { margin-bottom: 8px; }
.empty-tip { text-align: center; padding: 12px; color: var(--cpa-text-secondary); font-size: 13px; }
.goals p { font-size: 14px; margin-bottom: 6px; line-height: 1.6; }
</style>
