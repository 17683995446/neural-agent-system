<template>
  <div class="page-container diagnosis-page">
    <h1 class="page-title">🧠 AI 智能诊断</h1>

    <el-steps :active="step" align-center class="diag-steps">
      <el-step title="选择科目" />
      <el-step title="诊断模式" />
      <el-step title="答题诊断" />
      <el-step title="诊断报告" />
    </el-steps>

    <div v-if="step === 0" class="step-content">
      <h3>请选择要诊断的科目</h3>
      <div class="subject-grid">
        <div v-for="s in subjectList" :key="s.key" class="subject-option" :class="{ selected: selectedSubjects.includes(s.key), ['subject-bg-' + s.key]: selectedSubjects.includes(s.key) }" @click="toggleSubject(s.key)">
          <span class="subj-icon">{{ s.icon }}</span>
          <span class="subj-name">{{ s.name }}</span>
        </div>
      </div>
      <el-button type="primary" size="large" :disabled="selectedSubjects.length === 0" @click="step = 1">下一步</el-button>
    </div>

    <div v-if="step === 1" class="step-content">
      <h3>选择诊断模式</h3>
      <el-row :gutter="20">
        <el-col :span="12">
          <el-card shadow="hover" class="mode-card" :class="{ active: mode === 'quick' }" @click="mode = 'quick'">
            <h4>⚡ 快速诊断</h4>
            <p>每科10题，约15分钟，快速了解知识掌握概况</p>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover" class="mode-card" :class="{ active: mode === 'deep' }" @click="mode = 'deep'">
            <h4>🔬 深度诊断</h4>
            <p>每科30题，约45分钟，全面深入分析薄弱知识点</p>
          </el-card>
        </el-col>
      </el-row>
      <div class="step-actions">
        <el-button @click="step = 0">上一步</el-button>
        <el-button type="primary" size="large" @click="startDiagnosis">开始诊断</el-button>
      </div>
    </div>

    <div v-if="step === 2" class="step-content">
      <div v-if="diagLoading" class="loading-box">
        <el-icon class="is-loading" :size="48"><Loading /></el-icon>
        <p>AI正在生成诊断题目...</p>
      </div>
      <div v-else>
        <div class="diag-progress">
          <span>科目：{{ currentDiagSubject }}</span>
          <span>{{ diagIndex + 1 }} / {{ diagQuestions.length }}</span>
        </div>
        <el-progress :percentage="((diagIndex + 1) / diagQuestions.length * 100)" :stroke-width="8" />
        <div class="diag-question" v-if="diagQuestions[diagIndex]">
          <QuestionCard :question="diagQuestions[diagIndex]" />
          <AnswerInput :question="diagQuestions[diagIndex]" v-model="diagAnswer" />
          <div class="diag-actions">
            <el-button type="primary" @click="submitDiagAnswer" :disabled="!diagAnswer">提交答案</el-button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="step === 3" class="step-content">
      <h3>📊 诊断报告</h3>
      <el-row :gutter="20">
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header><span>知识掌握雷达图</span></template>
            <KnowledgeRadar :data="radarData" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header><span>薄弱知识点</span></template>
            <el-table :data="weakPoints" stripe size="small">
              <el-table-column prop="knowledge" label="知识点" />
              <el-table-column prop="mastery" label="掌握度">
                <template #default="{ row }">
                  <el-progress :percentage="row.mastery" :color="row.mastery < 40 ? '#f5222d' : row.mastery < 70 ? '#faad14' : '#52c41a'" />
                </template>
              </el-table-column>
              <el-table-column prop="subject" label="科目" width="80" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>
      <div class="report-actions">
        <el-button type="primary" size="large" @click="$router.push('/practice')">开始智能刷题</el-button>
        <el-button size="large" @click="$router.push('/study-plan')">生成学习计划</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { aiApi } from '../api/ai'
import { ElMessage } from 'element-plus'
import QuestionCard from '../components/QuestionCard.vue'
import AnswerInput from '../components/AnswerInput.vue'
import KnowledgeRadar from '../components/KnowledgeRadar.vue'

const step = ref(0)
const selectedSubjects = ref([])
const mode = ref('quick')
const diagLoading = ref(false)
const diagQuestions = ref([])
const diagIndex = ref(0)
const diagAnswer = ref(null)
const diagAnswers = ref([])
const radarData = ref({})
const weakPoints = ref([])

const subjectList = [
  { key: 'accounting', name: '会计', icon: '📊' },
  { key: 'audit', name: '审计', icon: '🔍' },
  { key: 'fm', name: '财管', icon: '📈' },
  { key: 'ecl', name: '经济法', icon: '⚖️' },
  { key: 'tax', name: '税法', icon: '💰' },
  { key: 'strategy', name: '战略', icon: '🎯' }
]

const subjectNameMap = { accounting: '会计', audit: '审计', fm: '财管', ecl: '经济法', tax: '税法', strategy: '战略' }

const currentDiagSubject = computed(() => {
  if (diagQuestions.value[diagIndex.value]) return subjectNameMap[diagQuestions.value[diagIndex.value].subject] || ''
  return ''
})

const toggleSubject = (key) => {
  const idx = selectedSubjects.value.indexOf(key)
  if (idx >= 0) selectedSubjects.value.splice(idx, 1)
  else selectedSubjects.value.push(key)
}

const startDiagnosis = async () => {
  step.value = 2
  diagLoading.value = true
  try {
    const res = await aiApi.diagnosis({ subjects: selectedSubjects.value, mode: mode.value })
    diagQuestions.value = res.data.questions || []
    diagIndex.value = 0
    diagAnswers.value = []
  } catch {} finally {
    diagLoading.value = false
  }
}

const submitDiagAnswer = async () => {
  diagAnswers.value.push({ question_id: diagQuestions.value[diagIndex.value].id, answer: diagAnswer.value })
  if (diagIndex.value < diagQuestions.value.length - 1) {
    diagIndex.value++
    diagAnswer.value = diagQuestions.value[diagIndex.value]?.q_type === 'multiple_choice' ? [] : ''
  } else {
    try {
      const res = await aiApi.diagnosisSubmit({ answers: diagAnswers.value, subjects: selectedSubjects.value, mode: mode.value })
      radarData.value = res.data.radar || {}
      weakPoints.value = res.data.weak_points || []
      step.value = 3
      ElMessage.success('诊断完成！')
    } catch {}
  }
}
</script>

<style scoped>
.diagnosis-page { max-width: 900px; margin: 0 auto; }
.diag-steps { margin-bottom: 32px; }
.step-content { text-align: center; }
.step-content h3 { margin-bottom: 24px; font-size: 20px; }
.subject-grid { display: flex; flex-wrap: wrap; gap: 16px; justify-content: center; margin-bottom: 24px; }
.subject-option { width: 120px; height: 100px; border: 2px solid #e8e8e8; border-radius: 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s; }
.subject-option:hover { border-color: var(--cpa-primary); }
.subject-option.selected { border-width: 2px; }
.subj-icon { font-size: 32px; margin-bottom: 4px; }
.subj-name { font-size: 15px; font-weight: 500; }
.mode-card { cursor: pointer; text-align: center; padding: 20px; transition: all 0.3s; border: 2px solid transparent; }
.mode-card.active { border-color: var(--cpa-primary); background: var(--cpa-primary-light); }
.mode-card h4 { font-size: 18px; margin-bottom: 8px; }
.mode-card p { font-size: 14px; color: var(--cpa-text-secondary); }
.step-actions { margin-top: 24px; display: flex; justify-content: center; gap: 12px; }
.loading-box { padding: 60px 0; }
.loading-box p { margin-top: 12px; color: var(--cpa-text-secondary); }
.diag-progress { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 14px; color: var(--cpa-text-secondary); }
.diag-question { text-align: left; margin-top: 20px; }
.diag-actions { margin-top: 16px; text-align: center; }
.report-actions { margin-top: 24px; display: flex; justify-content: center; gap: 12px; }
</style>
