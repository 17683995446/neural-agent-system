<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GaugeChart, LineChart, HeatmapChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent, VisualMapComponent, LegendComponent } from 'echarts/components'

use([CanvasRenderer, GaugeChart, LineChart, HeatmapChart, BarChart, TitleComponent, TooltipComponent, GridComponent, VisualMapComponent, LegendComponent])

const agents = ['input', 'conv', 'pool', 'fc1', 'fc2', 'fc3', 'output']
const trustData = ref([
  [1.0, 0.8, 0.6, 0.9, 1.2, 0.7, 1.0],
  [0.8, 1.0, 1.1, 0.7, 0.9, 0.8, 0.6],
  [0.6, 1.1, 1.0, 0.5, 0.8, 1.3, 0.7],
  [0.9, 0.7, 0.5, 1.0, 1.5, 0.6, 0.8],
  [1.2, 0.9, 0.8, 1.5, 1.0, 0.9, 1.1],
  [0.7, 0.8, 1.3, 0.6, 0.9, 1.0, 0.5],
  [1.0, 0.6, 0.7, 0.8, 1.1, 0.5, 1.0],
])

const qpsHistory = ref([])
const latencyHistory = ref([])
const timeLabels = ref([])
let timer = null

const simulateMetrics = () => {
  const now = new Date()
  timeLabels.value.push(now.toLocaleTimeString())
  qpsHistory.value.push(2.5 + Math.random() * 3)
  latencyHistory.value.push(200 + Math.random() * 800)
  if (timeLabels.value.length > 30) {
    timeLabels.value.shift()
    qpsHistory.value.shift()
    latencyHistory.value.shift()
  }
}

onMounted(() => { simulateMetrics(); timer = setInterval(simulateMetrics, 2000) })
onUnmounted(() => clearInterval(timer))

const trustHeatmapOption = ref({
  tooltip: { position: 'top' },
  grid: { top: '12%', bottom: '15%', left: '15%', right: '5%' },
  xAxis: { type: 'category', data: agents, splitArea: { show: true }, axisLabel: { color: '#8888a8' } },
  yAxis: { type: 'category', data: agents, splitArea: { show: true }, axisLabel: { color: '#8888a8' } },
  visualMap: { min: 0, max: 2, calculable: true, orient: 'horizontal', left: 'center', bottom: '0%', inRange: { color: ['#1a1a2e', '#6366f1', '#10b981', '#f59e0b'] }, textStyle: { color: '#8888a8' } },
  series: [{ name: '信任度', type: 'heatmap', data: trustData.value.flatMap((row, y) => row.map((v, x) => [x, y, v.toFixed(2)])), label: { show: true, color: '#e8e8f0', fontSize: 11 }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } } }],
})

const qpsLineOption = ref({
  tooltip: { trigger: 'axis' },
  legend: { data: ['QPS', '延迟(ms)'], textStyle: { color: '#8888a8' } },
  grid: { top: '15%', bottom: '10%', left: '10%', right: '10%' },
  xAxis: { type: 'category', data: timeLabels, axisLabel: { color: '#8888a8', fontSize: 10 } },
  yAxis: [
    { type: 'value', name: 'QPS', axisLabel: { color: '#8888a8' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
    { type: 'value', name: '延迟(ms)', axisLabel: { color: '#8888a8' }, splitLine: { show: false } },
  ],
  series: [
    { name: 'QPS', type: 'line', smooth: true, data: qpsHistory, lineStyle: { color: '#6366f1' }, itemStyle: { color: '#6366f1' }, areaStyle: { color: 'rgba(99,102,241,0.1)' } },
    { name: '延迟(ms)', type: 'line', smooth: true, yAxisIndex: 1, data: latencyHistory, lineStyle: { color: '#f59e0b' }, itemStyle: { color: '#f59e0b' } },
  ],
})

const circuitGaugeOption = ref({
  series: [
    { type: 'gauge', startAngle: 200, endAngle: -20, min: 0, max: 100, progress: { show: true, width: 12, itemStyle: { color: '#6366f1' } }, axisLine: { lineStyle: { width: 12, color: [[1, 'rgba(255,255,255,0.1)']] } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false }, anchor: { show: true, showAbove: true, size: 14, itemStyle: { borderWidth: 4, borderColor: '#6366f1' } }, title: { show: false }, detail: { valueAnimation: true, fontSize: 28, color: '#e8e8f0', offsetCenter: [0, '30%'], formatter: '{value}%' }, data: [{ value: 72 }] },
  ],
})

const rateLimiterBarOption = ref({
  tooltip: {},
  xAxis: { type: 'category', data: ['SMALL', 'MEDIUM', 'LARGE', 'XLARGE'], axisLabel: { color: '#8888a8' } },
  yAxis: { type: 'value', axisLabel: { color: '#8888a8' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
  legend: { data: ['max_qps', 'max_concurrent'], textStyle: { color: '#8888a8' } },
  series: [
    { name: 'max_qps', type: 'bar', data: [5, 3, 3, 2], itemStyle: { color: '#06b6d4' } },
    { name: 'max_concurrent', type: 'bar', data: [3, 3, 5, 3], itemStyle: { color: '#8b5cf6' } },
  ],
})
</script>

<template>
  <div>
    <div class="page-header">
      <el-icon :size="24" color="var(--accent-cyan)"><DataLine /></el-icon>
      <h2>实时仪表盘</h2>
      <el-tag type="warning" size="small" style="margin-left:auto;">模拟数据(2s刷新)</el-tag>
    </div>
    <el-row :gutter="20">
      <el-col :span="12">
        <div class="chart-card" style="margin-bottom:20px;">
          <div style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--text-primary);">信任度矩阵热力图 (7×7 Agent)</div>
          <VChart :option="trustHeatmapOption" style="height:360px;" autoresize />
        </div>
      </el-col>
      <el-col :span="12">
        <div class="chart-card" style="margin-bottom:20px;">
          <div style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--text-primary);">QPS / 延迟实时曲线</div>
          <VChart :option="qpsLineOption" style="height:360px;" autoresize />
        </div>
      </el-col>
    </el-row>
    <el-row :gutter="20">
      <el-col :span="8">
        <div class="chart-card" style="margin-bottom:20px;">
          <div style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--text-primary);">熔断器健康度</div>
          <VChart :option="circuitGaugeOption" style="height:240px;" autoresize />
          <div style="text-align:center;margin-top:8px;">
            <el-tag type="success" size="small">CLOSED</el-tag>
            <span style="color:var(--text-muted);font-size:12px;margin-left:8px;">failure_count: 1/5</span>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="chart-card" style="margin-bottom:20px;">
          <div style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--text-primary);">ScalabilityProfile限频配置</div>
          <VChart :option="rateLimiterBarOption" style="height:240px;" autoresize />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="chart-card">
          <div style="font-size:14px;font-weight:600;margin-bottom:16px;color:var(--text-primary);">系统概览</div>
          <el-descriptions :column="1" size="small" border style="--el-descriptions-item-bordered-label-background:var(--bg-tertiary);">
            <el-descriptions-item label="Tree-sitter">9语言 ✅</el-descriptions-item>
            <el-descriptions-item label="ASTCache">LRU+磁盘 ✅</el-descriptions-item>
            <el-descriptions-item label="合并防线">4层 ✅</el-descriptions-item>
            <el-descriptions-item label="共识引擎">4策略 ✅</el-descriptions-item>
            <el-descriptions-item label="双记忆">读写 ✅</el-descriptions-item>
            <el-descriptions-item label="单元测试">215通过 ✅</el-descriptions-item>
            <el-descriptions-item label="acomplete限频">已对齐 ✅</el-descriptions-item>
            <el-descriptions-item label="SafePickle">HMAC ✅</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>
    </el-row>
  </div>
</template>
