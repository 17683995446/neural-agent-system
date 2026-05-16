<template>
  <div class="chat-bubble" :class="message.role">
    <div class="bubble-avatar">
      <span v-if="message.role === 'user'">👤</span>
      <span v-else>🤖</span>
    </div>
    <div class="bubble-content">
      <div class="bubble-name">{{ message.role === 'user' ? '我' : 'AI助手' }}</div>
      <div class="bubble-text" v-html="formattedContent"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ message: { type: Object, required: true } })

const formattedContent = computed(() => {
  let content = props.message.content || ''
  content = content.replace(/\n/g, '<br>')
  return content
})
</script>

<style scoped>
.chat-bubble { display: flex; gap: 12px; margin-bottom: 16px; }
.chat-bubble.assistant { flex-direction: row; }
.chat-bubble.user { flex-direction: row-reverse; }
.bubble-avatar { width: 36px; height: 36px; border-radius: 50%; background: #f0f0f0; display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
.bubble-content { max-width: 70%; }
.bubble-name { font-size: 12px; color: var(--cpa-text-secondary); margin-bottom: 4px; }
.user .bubble-name { text-align: right; }
.bubble-text { padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.7; }
.assistant .bubble-text { background: #f6f8fa; color: var(--cpa-text); }
.user .bubble-text { background: var(--cpa-primary); color: #fff; }
</style>
