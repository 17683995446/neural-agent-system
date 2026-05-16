<template>
  <div class="exam-take-page">
    <div class="exam-top-bar">
      <div class="exam-title">{{ examStore.currentPaper?.title || '考试进行中' }}</div>
      <ExamTimer :time-left="examStore.timeLeft" :total="examStore.totalTime" />
      <el-button type="danger" @click="confirmSubmit">交卷</el-button>
    </div>

    <div class="exam-body" v-if="examStore.currentPaper">
      <div class="exam-sidebar">
        <h4>答题卡</h4>
        <div class="answer-sheet">
          <div v-for="(q, i) in examStore.currentPaper.questions" :key="i" class="sheet-item" :class="{ answered: examStore.answers[q.id], current: examStore.currentQuestionIndex === i, marked: examStore.markedQuestions.has(i) }" @click="examStore.currentQuestionIndex = i">
            {{ i + 1 }}
          </div>
        </div>
        <div class="sheet-legend">
          <span>🟢 已答</span><span>🔵 当前</span><span>🟡 标记</span><span>⚪ 未答</span>
        </div>
      </div>

      <div class="exam-main">
        <div class="question-header" v-if="examStore.currentQuestion">
          <span class="q-number">第 {{ examStore.currentQuestionIndex + 1 }} 题（共 {{ examStore.totalQuestions }} 题）</span>
          <el-button size="small" :type="examStore.markedQuestions.has(examStore.currentQuestionIndex) ? 'warning' : 'default'" @click="examStore.toggleMark(examStore.currentQuestionIndex)">
            {{ examStore.markedQuestions.has(examStore.currentQuestionIndex) ? '取消标记' : '标记' }}
          </el-button>
        </div>
        <QuestionCard v-if="examStore.currentQuestion" :question="examStore.currentQuestion" />
        <AnswerInput v-if="examStore.currentQuestion" :question="examStore.currentQuestion" v-model="currentAnswer" />
        <div class="nav-buttons">
          <el-button :disabled="examStore.currentQuestionIndex === 0" @click="examStore.currentQuestionIndex--">上一题</el-button>
          <el-button :disabled="examStore.currentQuestionIndex === examStore.totalQuestions - 1" @click="examStore.currentQuestionIndex++">下一题</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="submitDialog" title="确认交卷" width="400">
      <p>您已答 <strong>{{ examStore.answeredCount }}</strong> / {{ examStore.totalQuestions }} 题</p>
      <p v-if="examStore.totalQuestions - examStore.answeredCount > 0" style="color:var(--cpa-error)">
        还有 {{ examStore.totalQuestions - examStore.answeredCount }} 题未作答！
      </p>
      <template #footer>
        <el-button @click="submitDialog = false">继续答题</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="examStore.submitting">确认交卷</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useExamStore } from '../stores/exam'
import { ElMessage } from 'element-plus'
import QuestionCard from '../components/QuestionCard.vue'
import AnswerInput from '../components/AnswerInput.vue'
import ExamTimer from '../components/ExamTimer.vue'

const route = useRoute()
const router = useRouter()
const examStore = useExamStore()
const submitDialog = ref(false)

const currentAnswer = computed({
  get: () => examStore.answers[examStore.currentQuestion?.id] ?? (examStore.currentQuestion?.q_type === 'multiple_choice' ? [] : ''),
  set: (val) => { if (examStore.currentQuestion) examStore.setAnswer(examStore.currentQuestion.id, val) }
})

const confirmSubmit = () => { submitDialog.value = true }

const handleSubmit = async () => {
  try {
    const result = await examStore.submit()
    submitDialog.value = false
    ElMessage.success('交卷成功')
    router.push(`/exam/result/${result.id}`)
  } catch {}
}

onMounted(async () => {
  await examStore.startExam(route.params.id)
})

onBeforeUnmount(() => {
  examStore.stopTimer()
})
</script>

<style scoped>
.exam-take-page { height: calc(100vh - 60px); display: flex; flex-direction: column; background: #f0f2f5; }
.exam-top-bar { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; background: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.06); }
.exam-title { font-size: 16px; font-weight: 600; }
.exam-body { flex: 1; display: flex; overflow: hidden; }
.exam-sidebar { width: 220px; background: #fff; padding: 16px; overflow-y: auto; border-right: 1px solid #e8e8e8; }
.exam-sidebar h4 { margin-bottom: 12px; }
.answer-sheet { display: flex; flex-wrap: wrap; gap: 6px; }
.sheet-item { width: 32px; height: 32px; border: 1px solid #d9d9d9; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.sheet-item.answered { background: #52c41a; color: #fff; border-color: #52c41a; }
.sheet-item.current { border-color: #1890ff; box-shadow: 0 0 0 2px rgba(24,144,255,0.2); }
.sheet-item.marked { background: #faad14; color: #fff; border-color: #faad14; }
.sheet-legend { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: var(--cpa-text-secondary); }
.exam-main { flex: 1; padding: 24px; overflow-y: auto; }
.question-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.q-number { font-size: 15px; font-weight: 500; }
.nav-buttons { margin-top: 20px; display: flex; justify-content: center; gap: 12px; }
</style>
