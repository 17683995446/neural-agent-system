<template>
  <div class="page-container practice-page">
    <div class="practice-header">
      <h2>🎯 智能刷题</h2>
      <div class="practice-meta" v-if="current">
        <SubjectBadge :subject="current.subject" />
        <el-tag size="small" :type="difficultyType(current.difficulty)">{{ difficultyLabel(current.difficulty) }}</el-tag>
        <span class="practice-counter">{{ index + 1 }} / {{ questions.length }}</span>
      </div>
    </div>

    <div v-if="loading" class="loading-box">
      <el-icon class="is-loading" :size="48"><Loading /></el-icon>
      <p>AI正在为您推荐题目...</p>
    </div>

    <div v-else-if="!current" class="empty-box">
      <p>暂无推荐题目</p>
      <el-button type="primary" @click="loadRecommend">获取推荐题目</el-button>
    </div>

    <div v-else class="practice-content">
      <el-card shadow="hover" class="question-card">
        <div class="q-meta">
          <span v-if="current.knowledge_point" class="q-knowledge">📌 {{ current.knowledge_point }}</span>
        </div>
        <QuestionCard :question="current" />
        <AnswerInput :question="current" v-model="answer" :disabled="!!gradeResult" />

        <div v-if="!gradeResult" class="practice-actions">
          <el-button type="primary" :disabled="!answer" @click="handleGrade">提交答案</el-button>
          <el-button @click="handleSkip">跳过</el-button>
        </div>

        <div v-if="gradeResult" class="grade-result">
          <el-alert :title="gradeResult.is_correct ? '回答正确！' : '回答错误'" :type="gradeResult.is_correct ? 'success' : 'error'" show-icon :closable="false" />
          <div v-if="gradeResult.explanation" class="explanation">
            <h4>解析</h4>
            <p>{{ gradeResult.explanation }}</p>
          </div>
          <el-button v-if="!showExplain" type="warning" @click="handleExplain">AI详细解析</el-button>
          <div v-if="explanation" class="ai-explain">
            <h4>AI深度解析</h4>
            <div v-html="explanation"></div>
          </div>
          <el-button type="primary" @click="handleNext" style="margin-top:12px">{{ index < questions.length - 1 ? '下一题' : '完成练习' }}</el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { aiApi } from '../api/ai'
import QuestionCard from '../components/QuestionCard.vue'
import AnswerInput from '../components/AnswerInput.vue'
import SubjectBadge from '../components/SubjectBadge.vue'

const router = useRouter()
const loading = ref(false)
const questions = ref([])
const index = ref(0)
const current = ref(null)
const answer = ref(null)
const gradeResult = ref(null)
const explanation = ref(null)
const showExplain = ref(false)

const difficultyType = (d) => { if (d === 'easy' || d === 1) return 'success'; if (d === 'medium' || d === 2) return 'warning'; return 'danger' }
const difficultyLabel = (d) => { if (d === 'easy' || d === 1) return '简单'; if (d === 'medium' || d === 2) return '中等'; return '困难' }

const loadRecommend = async () => {
  loading.value = true
  try {
    const res = await aiApi.recommend({ count: 10 })
    questions.value = res.data || []
    index.value = 0
    current.value = questions.value[0] || null
  } catch {} finally {
    loading.value = false
  }
}

const handleGrade = async () => {
  try {
    const res = await aiApi.grade({ question_id: current.value.id, answer: answer.value })
    gradeResult.value = res.data
  } catch {}
}

const handleExplain = async () => {
  showExplain.value = true
  try {
    const res = await aiApi.explain({ question_id: current.value.id, answer: answer.value })
    explanation.value = res.data.explanation || res.data
  } catch {}
}

const handleSkip = () => handleNext()

const handleNext = () => {
  if (index.value < questions.value.length - 1) {
    index.value++
    current.value = questions.value[index.value]
    answer.value = current.value?.q_type === 'multiple_choice' ? [] : ''
    gradeResult.value = null
    explanation.value = null
    showExplain.value = false
  } else {
    router.push('/dashboard')
  }
}

onMounted(() => loadRecommend())
</script>

<style scoped>
.practice-page { max-width: 800px; margin: 0 auto; }
.practice-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.practice-meta { display: flex; align-items: center; gap: 8px; }
.practice-counter { font-size: 14px; color: var(--cpa-text-secondary); }
.loading-box, .empty-box { text-align: center; padding: 60px 0; }
.loading-box p, .empty-box p { margin-top: 12px; color: var(--cpa-text-secondary); }
.q-meta { margin-bottom: 8px; }
.q-knowledge { font-size: 13px; color: var(--cpa-text-secondary); }
.practice-actions { margin-top: 16px; display: flex; gap: 12px; }
.grade-result { margin-top: 20px; }
.explanation, .ai-explain { margin-top: 12px; padding: 12px; background: #f6f8fa; border-radius: 8px; }
.explanation h4, .ai-explain h4 { margin-bottom: 8px; color: var(--cpa-primary); }
.explanation p, .ai-explain p { font-size: 14px; line-height: 1.8; }
</style>
