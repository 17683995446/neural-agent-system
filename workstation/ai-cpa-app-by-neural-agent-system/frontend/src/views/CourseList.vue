<template>
  <div class="page-container course-list-page">
    <h1 class="page-title">📖 课程中心</h1>
    <el-form :inline="true" :model="filter" @submit.prevent>
      <el-form-item label="科目">
        <el-select v-model="filter.subject" placeholder="全部科目" clearable @change="fetchData">
          <el-option v-for="s in subjectList" :key="s.key" :label="s.name" :value="s.key" />
        </el-select>
      </el-form-item>
    </el-form>

    <div v-loading="loading" class="card-grid card-grid-3" style="margin-top:16px">
      <el-card v-for="c in courses" :key="c.id" shadow="hover" class="course-card" @click="$router.push(`/course/${c.id}`)">
        <div class="course-cover">{{ c.subject === 'accounting' ? '📊' : c.subject === 'audit' ? '🔍' : c.subject === 'fm' ? '📈' : c.subject === 'ecl' ? '⚖️' : c.subject === 'tax' ? '💰' : '🎯' }}</div>
        <div class="course-info">
          <h3>{{ c.title }}</h3>
          <SubjectBadge :subject="c.subject" />
          <p class="course-desc">{{ c.description }}</p>
          <div class="course-meta">
            <span>📚 {{ c.chapter_count || 0 }} 章节</span>
            <span>⏱️ {{ c.duration || 0 }} 课时</span>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { courseApi } from '../api/courses'
import SubjectBadge from '../components/SubjectBadge.vue'

const loading = ref(false)
const courses = ref([])
const filter = reactive({ subject: '' })
const subjectList = [
  { key: 'accounting', name: '会计' }, { key: 'audit', name: '审计' }, { key: 'fm', name: '财管' },
  { key: 'ecl', name: '经济法' }, { key: 'tax', name: '税法' }, { key: 'strategy', name: '战略' }
]

const fetchData = async () => {
  loading.value = true
  try {
    const params = {}
    if (filter.subject) params.subject = filter.subject
    const res = await courseApi.getCourses(params)
    courses.value = res.data || []
  } catch {} finally {
    loading.value = false
  }
}

onMounted(() => fetchData())
</script>

<style scoped>
.course-card { cursor: pointer; transition: transform 0.3s; }
.course-card:hover { transform: translateY(-4px); }
.course-cover { font-size: 48px; text-align: center; margin-bottom: 12px; }
.course-info h3 { font-size: 16px; margin-bottom: 8px; }
.course-desc { font-size: 13px; color: var(--cpa-text-secondary); margin: 8px 0; line-height: 1.5; }
.course-meta { display: flex; gap: 16px; font-size: 12px; color: var(--cpa-text-secondary); }
</style>
