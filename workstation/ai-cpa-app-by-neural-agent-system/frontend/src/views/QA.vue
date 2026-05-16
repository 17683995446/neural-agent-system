<template>
  <div class="page-container qa-page">
    <h1 class="page-title">💬 AI 智能答疑</h1>
    <el-row :gutter="20">
      <el-col :xs="24" :sm="18">
        <el-card shadow="hover" class="chat-card">
          <div class="chat-messages" ref="messagesRef">
            <div v-if="messages.length === 0" class="chat-welcome">
              <h3>👋 您好！我是CPA智能答疑助手</h3>
              <p>我可以帮您解答注册会计师考试相关问题，包括会计、审计、财管、经济法、税法、战略六科内容。</p>
              <div class="quick-questions">
                <el-button v-for="q in quickQuestions" :key="q" @click="sendQuick(q)">{{ q }}</el-button>
              </div>
            </div>
            <AIChatBubble v-for="(m, i) in messages" :key="i" :message="m" />
          </div>
          <div class="chat-input-bar">
            <el-input v-model="input" placeholder="输入您的CPA问题..." size="large" @keyup.enter="sendMessage" :disabled="sending" />
            <el-button type="primary" size="large" @click="sendMessage" :loading="sending">发送</el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="6">
        <el-card shadow="hover">
          <template #header><span>📚 快速选题</span></template>
          <div class="subject-shortcuts">
            <div v-for="s in subjectList" :key="s.key" class="shortcut-item" @click="sendQuick(`请介绍${s.name}科目的考试重点`)">
              <span>{{ s.icon }}</span>
              <span>{{ s.name }}</span>
            </div>
          </div>
        </el-card>
        <el-card shadow="hover" style="margin-top:16px">
          <template #header><span>💡 学习建议</span></template>
          <p style="font-size:13px;color:var(--cpa-text-secondary);line-height:1.6">
            遇到不理解的知识点，可以让我详细解释。我会结合CPA考试大纲和历年真题为您分析。
          </p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { aiApi } from '../api/ai'
import AIChatBubble from '../components/AIChatBubble.vue'

const messagesRef = ref()
const messages = ref([])
const input = ref('')
const sending = ref(false)

const subjectList = [
  { key: 'accounting', name: '会计', icon: '📊' }, { key: 'audit', name: '审计', icon: '🔍' },
  { key: 'fm', name: '财管', icon: '📈' }, { key: 'ecl', name: '经济法', icon: '⚖️' },
  { key: 'tax', name: '税法', icon: '💰' }, { key: 'strategy', name: '战略', icon: '🎯' }
]

const quickQuestions = [
  '会计科目难点有哪些？',
  '审计程序如何理解？',
  '财管公式怎么记忆？',
  '经济法重点法条是什么？'
]

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
}

const sendMessage = async () => {
  if (!input.value.trim()) return
  messages.value.push({ role: 'user', content: input.value })
  const question = input.value
  input.value = ''
  sending.value = true
  scrollToBottom()
  try {
    const res = await aiApi.qa({ question })
    messages.value.push({ role: 'assistant', content: res.data.answer || res.data })
  } catch {} finally {
    sending.value = false
    scrollToBottom()
  }
}

const sendQuick = (q) => { input.value = q; sendMessage() }
</script>

<style scoped>
.chat-card { height: calc(100vh - 160px); display: flex; flex-direction: column; }
.chat-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.chat-messages { flex: 1; overflow-y: auto; padding: 16px; }
.chat-welcome { text-align: center; padding: 40px 20px; }
.chat-welcome h3 { margin-bottom: 12px; }
.chat-welcome p { color: var(--cpa-text-secondary); margin-bottom: 24px; }
.quick-questions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.chat-input-bar { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
.shortcut-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; cursor: pointer; font-size: 14px; }
.shortcut-item:hover { color: var(--cpa-primary); }
</style>
