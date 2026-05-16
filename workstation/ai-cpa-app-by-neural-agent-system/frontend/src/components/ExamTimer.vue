<template>
  <div class="exam-timer" :class="{ urgent: isUrgent, overtime: isOvertime }">
    <el-icon><Clock /></el-icon>
    <span class="time-display">{{ formattedTime }}</span>
    <el-progress v-if="total > 0" :percentage="percentage" :stroke-width="4" :show-text="false" :color="progressColor" class="timer-progress" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ timeLeft: { type: Number, default: 0 }, total: { type: Number, default: 0 } })

const hours = computed(() => Math.floor(props.timeLeft / 3600))
const minutes = computed(() => Math.floor((props.timeLeft % 3600) / 60))
const seconds = computed(() => props.timeLeft % 60)

const formattedTime = computed(() => {
  const h = hours.value
  const m = String(minutes.value).padStart(2, '0')
  const s = String(seconds.value).padStart(2, '0')
  return h > 0 ? `${h}:${m}:${s}` : `${m}:${s}`
})

const percentage = computed(() => props.total > 0 ? ((props.total - props.timeLeft) / props.total * 100) : 0)
const isUrgent = computed(() => props.timeLeft > 0 && props.timeLeft <= 600)
const isOvertime = computed(() => props.timeLeft <= 0)
const progressColor = computed(() => {
  if (isOvertime.value) return '#f5222d'
  if (isUrgent.value) return '#faad14'
  return '#1890ff'
})
</script>

<style scoped>
.exam-timer { display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 600; color: var(--cpa-text); }
.exam-timer.urgent { color: #faad14; }
.exam-timer.overtime { color: #f5222d; }
.time-display { font-variant-numeric: tabular-nums; }
.timer-progress { width: 100px; margin-left: 8px; }
</style>
