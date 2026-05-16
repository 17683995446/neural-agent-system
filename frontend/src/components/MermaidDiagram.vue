<script setup>
import { ref, onMounted, watch } from 'vue'
import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#6366f1',
    primaryTextColor: '#e8e8f0',
    primaryBorderColor: '#6366f1',
    lineColor: '#55556a',
    secondaryColor: '#1a1a2e',
    tertiaryColor: '#16162a',
    textColor: '#e8e8f0',
    fontSize: '13px',
  },
  flowchart: { curve: 'basis', padding: 20 },
  sequence: { actorMargin: 80, messageMargin: 40 },
})

const props = defineProps({ definition: { type: String, required: true } })
const container = ref(null)
const renderId = `mermaid-${Math.random().toString(36).slice(2, 9)}`

const render = async () => {
  if (!container.value || !props.definition) return
  try {
    const { svg } = await mermaid.render(renderId, props.definition)
    container.value.innerHTML = svg
  } catch (e) {
    container.value.innerHTML = `<p style="color:var(--accent-red);">Mermaid render error: ${e.message}</p>`
  }
}

onMounted(render)
watch(() => props.definition, render)
</script>

<template>
  <div class="mermaid-container" ref="container"></div>
</template>
