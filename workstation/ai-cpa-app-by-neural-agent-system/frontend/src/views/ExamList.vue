<template>
  <div class="page-container exam-list-page">
    <h1 class="page-title">📝 机考模拟</h1>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="模拟试卷" name="mock">
        <div v-loading="loading" class="paper-grid card-grid card-grid-2">
          <el-card v-for="p in mockPapers" :key="p.id" shadow="hover" class="paper-card">
            <div class="paper-header">
              <h3>{{ p.title }}</h3>
              <el-tag :type="p.type === 'mock' ? 'primary' : 'warning'">{{ p.type === 'mock' ? '模拟' : '真题' }}</el-tag>
            </div>
            <div class="paper-info">
              <span>📂 {{ subjectName(p.subject) }}</span>
              <span>⏱️ {{ p.duration || 150 }}分钟</span>
              <span>📋 {{ p.question_count || 0 }}题</span>
            </div>
            <div class="paper-desc">{{ p.description }}</div>
            <el-button type="primary" @click="startExam(p.id)">开始考试</el-button>
          </el-card>
        </div>
      </el-tab-pane>
      <el-tab-pane label="历年真题" name="past">
        <div v-loading="loading" class="paper-grid card-grid card-grid-2">
          <el-card v-for="p in pastPapers" :key="p.id" shadow="hover" class="paper-card">
            <div class="paper-header">
              <h3>{{ p.title }}</h3>
              <el-tag type="warning">真题</el-tag>
            </div>
            <div class="paper-info">
              <span>📂 {{ subjectName(p.subject) }}</span>
              <span>⏱️ {{ p.duration || 150 }}分钟</span>
              <span>📋 {{ p.question_count || 0 }}题</span>
            </div>
            <div class="paper-desc">{{ p.description }}</div>
            <el-button type="primary" @click="startExam(p.id)">开始考试</el-button>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { examApi } from '../api/exam'

const router = useRouter()
const loading = ref(false)
const papers = ref([])
const activeTab = ref('mock')

const subjectName = (s) => ({ accounting: '会计', audit: '审计', fm: '财管', ecl: '经济法', tax: '税法', strategy: '战略' }[s] || s)
const mockPapers = computed(() => papers.value.filter(p => p.type === 'mock'))
const pastPapers = computed(() => papers.value.filter(p => p.type === 'past'))

const startExam = (id) => router.push(`/exam/${id}`)

onMounted(async () => {
  loading.value = true
  try { const res = await examApi.getPapers(); papers.value = res.data || [] } catch {} finally { loading.value = false }
})
</script>

<style scoped>
.paper-card { transition: transform 0.3s; }
.paper-card:hover { transform: translateY(-4px); }
.paper-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.paper-header h3 { font-size: 16px; }
.paper-info { display: flex; gap: 16px; margin-bottom: 8px; font-size: 13px; color: var(--cpa-text-secondary); }
.paper-desc { font-size: 13px; color: var(--cpa-text-secondary); margin-bottom: 16px; line-height: 1.5; }
</style>
