<template>
  <div class="answer-input">
    <div v-if="isSingleChoice" class="radio-group">
      <el-radio-group v-model="answer" :disabled="disabled">
        <el-radio v-for="opt in options" :key="opt.key" :value="opt.key">{{ opt.key }}. {{ opt.text || opt }}</el-radio>
      </el-radio-group>
    </div>
    <div v-else-if="isMultipleChoice" class="checkbox-group">
      <el-checkbox-group v-model="answer" :disabled="disabled">
        <el-checkbox v-for="opt in options" :key="opt.key" :value="opt.key" :label="`${opt.key}. ${opt.text || opt}`" />
      </el-checkbox-group>
    </div>
    <div v-else-if="isJudge" class="judge-group">
      <el-radio-group v-model="answer" :disabled="disabled">
        <el-radio value="true">正确</el-radio>
        <el-radio value="false">错误</el-radio>
      </el-radio-group>
    </div>
    <div v-else class="text-input">
      <el-input type="textarea" :rows="4" v-model="answer" :disabled="disabled" placeholder="请输入您的答案..." />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ question: { type: Object, required: true }, modelValue: { default: null }, disabled: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])

const getDefaultAnswer = () => {
  if (props.modelValue !== null && props.modelValue !== undefined) return props.modelValue
  const qt = props.question?.q_type
  if (qt === 'multiple_choice') return []
  return ''
}

const answer = ref(getDefaultAnswer())

watch(() => props.modelValue, (val) => {
  if (val === null || val === undefined) {
    answer.value = props.question?.q_type === 'multiple_choice' ? [] : ''
  } else {
    answer.value = val
  }
})

watch(answer, (val) => {
  emit('update:modelValue', val)
}, { deep: true })

watch(() => props.question?.q_type, () => {
  answer.value = props.question?.q_type === 'multiple_choice' ? [] : ''
  emit('update:modelValue', answer.value)
})

const qType = computed(() => props.question?.q_type || 'single_choice')
const options = computed(() => {
  const opts = props.question?.options || []
  return opts.map((o, i) => {
    if (typeof o === 'string') return { key: String.fromCharCode(65 + i), text: o }
    if (typeof o === 'object' && o.key) return o
    return { key: String.fromCharCode(65 + i), text: o.text || JSON.stringify(o) }
  })
})
const isSingleChoice = computed(() => qType.value === 'single_choice')
const isMultipleChoice = computed(() => qType.value === 'multiple_choice')
const isJudge = computed(() => qType.value === 'true_false')
</script>

<style scoped>
.radio-group, .checkbox-group, .judge-group { padding: 8px 0; }
.radio-group :deep(.el-radio), .checkbox-group :deep(.el-checkbox) { display: block; margin-bottom: 8px; }
</style>
