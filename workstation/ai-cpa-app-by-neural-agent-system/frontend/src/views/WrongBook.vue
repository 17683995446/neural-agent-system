<template>
  <div class="page-container wrong-book-page">
    <h1 class="page-title">❌ 错题本</h1>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" @submit.prevent>
        <el-form-item label="科目">
          <el-select v-model="filters.subject" placeholder="全部" clearable @change="fetchData" style="width:120px">
            <el-option v-for="s in subjectList" :key="s.key" :label="s.name" :value="s.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="题型">
          <el-select v-model="filters.q_type" placeholder="全部" clearable @change="fetchData" style="width:120px">
            <el-option label="单选" value="single_choice" /><el-option label="多选" value="multiple_choice" /><el-option label="判断" value="true_false" /><el-option label="简答" value="short_answer" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top:16px" v-loading="loading">
      <div v-if="wrongItems.length === 0" class="empty-tip">暂无错题，继续保持！</div>
      <div v-for="item in wrongItems" :key="item.id" class="wrong-item">
        <div class="wrong-header">
          <SubjectBadge :subject="item.subject" />
          <el-tag size="small" type="danger">错</el-tag>
          <span class="wrong-time">{{ item.created_at?.substring(0, 10) }}</span>
        </div>
        <div class="wrong-content">{{ item.content }}</div>
        <div class="wrong-answers">
          <span class="your-ans">您的答案：<em>{{ item.user_answer }}</em></span>
          <span class="correct-ans">正确答案：<em>{{ item.correct_answer }}</em></span>
        </div>
        <div class="wrong-actions">
          <el-button type="primary" size="small" @click="retryQuestion(item)">重做</el-button>
          <el-button size="small" @click="analyzeWrong(item)">AI分析</el-button>
        </div>
        <div v-if="item.ai_analysis" class="ai-analysis" v-html="item.ai_analysis"></div>
      </div>
      <div class="pagination-bar">
        <el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" @current-change="fetchData" />
      </div>
    </el-card>

    <el-dialog v-model="analysisDialog" title="AI错题分析" width="600">
      <div v-loading="analysisLoading">
        <div v-if="analysisResult" class="analysis-content" v-html="analysisResult"></div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { questionApi } from '../api/questions'
import { aiApi } from '../api/ai'
import SubjectBadge from '../components/SubjectBadge.vue'

const router = useRouter()
const loading = ref(false)
const wrongItems = ref([])
const total = ref(0)
const page = ref(1)
const filters = reactive({ subject: '', q_type: '' })
const analysisDialog = ref(false)
const analysisLoading = ref(false)
const analysisResult = ref('')

const subjectList = [
  { key: 'accounting', name: '会计' }, { key: 'audit', name: '审计' }, { key: 'fm', name: '财管' },
  { key: 'ecl', name: '经济法' }, { key: 'tax', name: '税法' }, { key: 'strategy', name: '战略' }
]

const fetchData = async () => {
  loading.value = true
  try {
    const params = { page: page.value, size: 20, wrong_only: true }
    if (filters.subject) params.subject = filters.subject
    if (filters.q_type) params.q_type = filters.q_type
    const res = await questionApi.getQuestions(params)
    wrongItems.value = res.data.items || res.data || []
    total.value = res.data.total || 0
  } catch {} finally { loading.value = false }
}

const retryQuestion = (item) => router.push({ path: '/practice', query: { question_id: item.id } })

const analyzeWrong = async (item) => {
  analysisDialog.value = true
  analysisLoading.value = true
  analysisResult.value = ''
  try {
    const res = await aiApi.wrongAnalysis({ question_id: item.id, user_answer: item.user_answer })
    analysisResult.value = res.data.analysis || res.data
  } catch {} finally { analysisLoading.value = false }
}

onMounted(() => fetchData())
</script>

<style scoped>
.filter-card :deep(.el-form-item) { margin-bottom: 0; }
.wrong-item { padding: 16px 0; border-bottom: 1px solid #f0f0f0; }
.wrong-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.wrong-time { font-size: 12px; color: var(--cpa-text-secondary); margin-left: auto; }
.wrong-content { font-size: 14px; margin-bottom: 8px; line-height: 1.6; }
.wrong-answers { font-size: 13px; margin-bottom: 8px; }
.wrong-answers span { margin-right: 16px; }
.your-ans em { color: var(--cpa-error); font-style: normal; }
.correct-ans em { color: var(--cpa-success); font-style: normal; }
.wrong-actions { margin-bottom: 8px; }
.ai-analysis { background: #f6f8fa; padding: 12px; border-radius: 8px; font-size: 14px; line-height: 1.8; }
.empty-tip { text-align: center; padding: 40px; color: var(--cpa-text-secondary); }
.pagination-bar { margin-top: 16px; text-align: right; }
.analysis-content { line-height: 1.8; font-size: 14px; }
</style>
