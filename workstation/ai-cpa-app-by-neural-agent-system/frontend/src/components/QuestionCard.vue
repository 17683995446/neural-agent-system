<template>
  <div class="question-card">
    <div class="q-content" v-html="formattedContent"></div>
    <div v-if="question.options && question.options.length" class="q-options">
      <div v-for="(opt, i) in question.options" :key="i" class="q-option" :class="{ correct: showAnswer && opt.is_correct, wrong: showAnswer && selectedOption === opt.key && !opt.is_correct }">
        <span class="opt-key">{{ opt.key || String.fromCharCode(65 + i) }}.</span>
        <span class="opt-text">{{ opt.text || opt }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ question: { type: Object, required: true }, showAnswer: { type: Boolean, default: false }, selectedOption: { type: String, default: '' } })

const formattedContent = computed(() => {
  let content = props.question.content || ''
  content = content.replace(/\n/g, '<br>')
  return content
})
</script>

<style scoped>
.q-content { font-size: 15px; line-height: 1.8; margin-bottom: 16px; }
.q-options { margin-top: 8px; }
.q-option { display: flex; align-items: flex-start; gap: 8px; padding: 8px 12px; margin-bottom: 6px; border-radius: 6px; border: 1px solid #e8e8e8; transition: all 0.2s; }
.q-option:hover { background: #f6f8fa; }
.q-option.correct { background: #f6ffed; border-color: #52c41a; }
.q-option.wrong { background: #fff1f0; border-color: #f5222d; }
.opt-key { font-weight: 600; color: var(--cpa-primary); flex-shrink: 0; }
.opt-text { font-size: 14px; line-height: 1.6; }
</style>
