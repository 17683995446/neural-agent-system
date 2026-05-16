<template>
  <div class="page-container question-bank-page">
    <h1 class="page-title">📚 题库</h1>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" @submit.prevent="handleSearch">
        <el-form-item label="科目">
          <el-select v-model="filters.subject" placeholder="全部科目" clearable style="width:120px">
            <el-option v-for="s in subjectList" :key="s.key" :label="s.name" :value="s.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="章节">
          <el-input v-model="filters.chapter" placeholder="章节" clearable style="width:120px" />
        </el-form-item>
        <el-form-item label="题型">
          <el-select v-model="filters.q_type" placeholder="全部题型" clearable style="width:120px">
            <el-option label="单选题" value="single_choice" />
            <el-option label="多选题" value="multiple_choice" />
            <el-option label="判断题" value="true_false" />
            <el-option label="简答题" value="short_answer" />
            <el-option label="计算题" value="calculation" />
            <el-option label="综合题" value="case_analysis" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="filters.difficulty" placeholder="全部难度" clearable style="width:100px">
            <el-option label="简单" value="easy" />
            <el-option label="中等" value="medium" />
            <el-option label="困难" value="hard" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="filters.keyword" placeholder="搜索题目" clearable style="width:160px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top:16px" v-loading="loading">
      <el-table :data="questions" stripe style="width:100%">
        <el-table-column type="index" width="50" label="#" />
        <el-table-column prop="subject" label="科目" width="80">
          <template #default="{ row }"><SubjectBadge :subject="row.subject" /></template>
        </el-table-column>
        <el-table-column label="题目内容" min-width="300">
          <template #default="{ row }">
            <span class="q-preview" @click="goPractice(row)">{{ row.content?.substring(0, 80) }}{{ row.content?.length > 80 ? '...' : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="q_type" label="题型" width="90">
          <template #default="{ row }"><el-tag size="small">{{ typeLabel(row.q_type) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="difficulty" label="难度" width="80">
          <template #default="{ row }">
            <span :class="'difficulty-' + row.difficulty">{{ difficultyLabel(row.difficulty) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="knowledge_point" label="知识点" width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="goPractice(row)">练习</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper" @current-change="fetchData" @size-change="fetchData" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { questionApi } from '../api/questions'
import SubjectBadge from '../components/SubjectBadge.vue'

const router = useRouter()
const loading = ref(false)
const questions = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)

const filters = reactive({ subject: '', chapter: '', q_type: '', difficulty: '', keyword: '' })

const subjectList = [
  { key: 'accounting', name: '会计' }, { key: 'audit', name: '审计' }, { key: 'fm', name: '财管' },
  { key: 'ecl', name: '经济法' }, { key: 'tax', name: '税法' }, { key: 'strategy', name: '战略' }
]

const typeLabel = (t) => ({ single_choice: '单选', multiple_choice: '多选', true_false: '判断', short_answer: '简答', calculation: '计算', case_analysis: '综合' }[t] || t)
const difficultyLabel = (d) => ({ easy: '简单', medium: '中等', hard: '困难', 1: '简单', 2: '中等', 3: '困难' }[d] || d)

const fetchData = async () => {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    Object.keys(filters).forEach(k => { if (filters[k]) params[k] = filters[k] })
    const res = await questionApi.getQuestions(params)
    questions.value = res.data.items || res.data || []
    total.value = res.data.total || 0
  } catch {} finally {
    loading.value = false
  }
}

const handleSearch = () => { page.value = 1; fetchData() }
const resetFilters = () => { Object.keys(filters).forEach(k => filters[k] = ''); handleSearch() }
const goPractice = (q) => router.push({ path: '/practice', query: { question_id: q.id } })

onMounted(() => fetchData())
</script>

<style scoped>
.filter-card :deep(.el-form-item) { margin-bottom: 0; }
.q-preview { cursor: pointer; font-size: 14px; color: var(--cpa-text); }
.q-preview:hover { color: var(--cpa-primary); }
.pagination-bar { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
