<template>
  <div class="page-container exam-result-page" v-loading="loading">
    <div v-if="result" class="result-content">
      <el-card shadow="hover" class="score-card">
        <h2>📊 考试结果</h2>
        <div class="score-main">
          <div class="score-circle" :class="passClass">
            <span class="score-value">{{ result.score }}</span>
            <span class="score-label">分</span>
          </div>
          <div class="score-info">
            <p>试卷：{{ result.paper_title }}</p>
            <p>用时：{{ formatTime(result.time_used) }}</p>
            <p>正确：{{ result.correct_count }} / {{ result.total_count }}</p>
            <p>正确率：{{ result.accuracy ? (result.accuracy * 100).toFixed(1) : 0 }}%</p>
            <el-tag :type="passClass" size="large">{{ result.score >= 60 ? '通过' : '未通过' }}</el-tag>
          </div>
        </div>
      </el-card>

      <el-row :gutter="20" style="margin-top:20px">
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header><span>AI分析报告</span></template>
            <div class="ai-report" v-html="result.ai_report || '暂无AI分析'"></div>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header><span>知识薄弱点</span></template>
            <div v-if="result.knowledge_gaps && result.knowledge_gaps.length">
              <div v-for="(g, i) in result.knowledge_gaps" :key="i" class="gap-item">
                <span>{{ g.knowledge }}</span>
                <el-progress :percentage="g.mastery || 0" :stroke-width="8" :color="g.mastery < 40 ? '#f5222d' : '#faad14'" />
              </div>
            </div>
            <div v-else class="empty-tip">暂无数据</div>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="hover" style="margin-top:20px">
        <template #header><span>逐题分析</span></template>
        <el-table :data="result.details || []" stripe size="small">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column label="题目" min-width="200">
            <template #default="{ row }">{{ row.content?.substring(0, 60) }}...</template>
          </el-table-column>
          <el-table-column label="您的答案" width="120" prop="user_answer" />
          <el-table-column label="正确答案" width="120" prop="correct_answer" />
          <el-table-column label="结果" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_correct ? 'success' : 'danger'" size="small">{{ row.is_correct ? '正确' : '错误' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <div class="result-actions">
        <el-button type="primary" size="large" @click="$router.push('/exam')">返回列表</el-button>
        <el-button size="large" @click="$router.push('/practice')">针对性练习</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { examApi } from '../api/exam'

const route = useRoute()
const loading = ref(false)
const result = ref(null)

const passClass = computed(() => result.value?.score >= 60 ? 'success' : 'danger')

const formatTime = (seconds) => {
  if (!seconds) return '0分0秒'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}分${s}秒`
}

onMounted(async () => {
  loading.value = true
  try { const res = await examApi.getResult(route.params.id); result.value = res.data } catch {} finally { loading.value = false }
})
</script>

<style scoped>
.score-card { text-align: center; padding: 20px; }
.score-main { display: flex; align-items: center; justify-content: center; gap: 40px; margin-top: 16px; }
.score-circle { width: 120px; height: 120px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 4px solid; }
.score-circle.success { border-color: #52c41a; color: #52c41a; }
.score-circle.danger { border-color: #f5222d; color: #f5222d; }
.score-value { font-size: 40px; font-weight: 700; }
.score-label { font-size: 14px; }
.score-info { text-align: left; }
.score-info p { margin-bottom: 8px; font-size: 14px; }
.ai-report { font-size: 14px; line-height: 1.8; }
.gap-item { margin-bottom: 12px; }
.gap-item span { font-size: 13px; display: block; margin-bottom: 4px; }
.empty-tip { text-align: center; padding: 20px; color: var(--cpa-text-secondary); }
.result-actions { margin-top: 24px; text-align: center; display: flex; justify-content: center; gap: 12px; }
</style>
