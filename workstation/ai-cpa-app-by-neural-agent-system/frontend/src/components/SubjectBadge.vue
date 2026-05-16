<template>
  <el-tag :class="'subject-tag-' + subject" :effect="effect" :size="size" :type="tagType">
    {{ subjectName }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ subject: { type: String, required: true }, size: { type: String, default: 'default' }, effect: { type: String, default: 'light' } })

const nameMap = { accounting: '会计', audit: '审计', fm: '财管', ecl: '经济法', tax: '税法', strategy: '战略' }
const typeMap = { accounting: '', audit: 'warning', fm: 'info', ecl: 'danger', tax: 'warning', strategy: 'success' }

const subjectName = computed(() => nameMap[props.subject] || props.subject)
const tagType = computed(() => typeMap[props.subject] || '')
</script>

<style scoped>
.subject-tag-accounting { color: #1890ff !important; border-color: #1890ff !important; }
.subject-tag-audit { color: #722ed1 !important; border-color: #722ed1 !important; }
.subject-tag-fm { color: #13c2c2 !important; border-color: #13c2c2 !important; }
.subject-tag-ecl { color: #eb2f96 !important; border-color: #eb2f96 !important; }
.subject-tag-tax { color: #fa8c16 !important; border-color: #fa8c16 !important; }
.subject-tag-strategy { color: #52c41a !important; border-color: #52c41a !important; }
</style>
