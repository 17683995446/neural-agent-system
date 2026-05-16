<template>
  <div ref="chartRef" class="radar-chart"></div>
</template>

<script setup>
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({ data: { type: Object, default: () => ({}) } })
const chartRef = ref()
let chart = null

const renderChart = () => {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)

  const indicators = props.data.indicators || [
    { name: '会计', max: 100 }, { name: '审计', max: 100 }, { name: '财管', max: 100 },
    { name: '经济法', max: 100 }, { name: '税法', max: 100 }, { name: '战略', max: 100 }
  ]
  const values = props.data.values || [65, 45, 55, 70, 40, 60]

  chart.setOption({
    tooltip: {},
    radar: { indicator: indicators, shape: 'polygon', splitNumber: 5, axisName: { color: '#666', fontSize: 12 } },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: '知识掌握度',
        areaStyle: { opacity: 0.2, color: '#1890ff' },
        lineStyle: { color: '#1890ff' },
        itemStyle: { color: '#1890ff' }
      }]
    }]
  })
}

const chartResizeHandler = () => chart?.resize()

onMounted(() => {
  renderChart()
  window.addEventListener('resize', chartResizeHandler)
})
watch(() => props.data, renderChart, { deep: true })
onBeforeUnmount(() => {
  window.removeEventListener('resize', chartResizeHandler)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.radar-chart { height: 300px; }
</style>
