<template>
  <div class="page-container course-detail-page" v-loading="loading">
    <div v-if="course" class="course-layout">
      <el-row :gutter="20">
        <el-col :xs="24" :sm="16">
          <el-card shadow="hover">
            <h2>{{ course.title }}</h2>
            <SubjectBadge :subject="course.subject" />
            <div class="video-player">
              <div class="video-placeholder">
                <el-icon :size="64"><VideoPlay /></el-icon>
                <p>视频播放器</p>
              </div>
            </div>
          </el-card>

          <el-card shadow="hover" style="margin-top:16px">
            <template #header><span>📝 章节列表</span></template>
            <el-collapse v-model="activeChapters">
              <el-collapse-item v-for="ch in course.chapters || []" :key="ch.id" :title="ch.title" :name="ch.id">
                <div v-for="sec in ch.sections || []" :key="sec.id" class="section-item" @click="playSection(sec)">
                  <el-icon><VideoPlay /></el-icon>
                  <span>{{ sec.title }}</span>
                  <span class="sec-duration">{{ sec.duration || 0 }}min</span>
                </div>
              </el-collapse-item>
            </el-collapse>
          </el-card>

          <el-card shadow="hover" style="margin-top:16px">
            <template #header><span>📒 笔记</span></template>
            <el-input v-model="noteContent" type="textarea" :rows="4" placeholder="记录学习笔记..." />
            <el-button type="primary" style="margin-top:8px" @click="saveNote">保存笔记</el-button>
          </el-card>
        </el-col>

        <el-col :xs="24" :sm="8">
          <el-card shadow="hover" class="qa-sidebar">
            <template #header><span>💬 AI答疑</span></template>
            <div class="qa-messages">
              <AIChatBubble v-for="(m, i) in qaMessages" :key="i" :message="m" />
            </div>
            <div class="qa-input">
              <el-input v-model="qaInput" placeholder="输入问题..." @keyup.enter="sendQA" />
              <el-button type="primary" @click="sendQA" :loading="qaLoading">发送</el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { courseApi } from '../api/courses'
import { aiApi } from '../api/ai'
import { ElMessage } from 'element-plus'
import SubjectBadge from '../components/SubjectBadge.vue'
import AIChatBubble from '../components/AIChatBubble.vue'

const route = useRoute()
const loading = ref(false)
const course = ref(null)
const activeChapters = ref([])
const noteContent = ref('')
const qaMessages = ref([])
const qaInput = ref('')
const qaLoading = ref(false)

const playSection = (sec) => {
  ElMessage.info(`播放：${sec.title}`)
}

const saveNote = async () => {
  if (!noteContent.value.trim()) return
  try {
    await courseApi.addNote(route.params.id, { content: noteContent.value })
    ElMessage.success('笔记已保存')
    noteContent.value = ''
  } catch {}
}

const sendQA = async () => {
  if (!qaInput.value.trim()) return
  qaMessages.value.push({ role: 'user', content: qaInput.value })
  const question = qaInput.value
  qaInput.value = ''
  qaLoading.value = true
  try {
    const res = await aiApi.qa({ question, context: `课程：${course.value?.title}` })
    qaMessages.value.push({ role: 'assistant', content: res.data.answer || res.data })
  } catch {} finally {
    qaLoading.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try { const res = await courseApi.getCourse(route.params.id); course.value = res.data; activeChapters.value = (res.data.chapters || []).map(c => c.id) } catch {} finally { loading.value = false }
})
</script>

<style scoped>
.video-player { margin: 20px 0; }
.video-placeholder { background: #000; color: #fff; height: 360px; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 8px; }
.video-placeholder p { margin-top: 12px; font-size: 14px; opacity: 0.7; }
.section-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; cursor: pointer; font-size: 14px; }
.section-item:hover { color: var(--cpa-primary); }
.sec-duration { margin-left: auto; font-size: 12px; color: var(--cpa-text-secondary); }
.qa-sidebar { position: sticky; top: 80px; }
.qa-messages { max-height: 400px; overflow-y: auto; margin-bottom: 12px; }
.qa-input { display: flex; gap: 8px; }
</style>
