<script setup lang="ts">
import { computed } from 'vue'
import type { ProgressGroup } from '../types'
import RadarChart from './RadarChart.vue'

const props = defineProps<{ group: ProgressGroup }>()

const attempts = computed(() => props.group.attempts)

const W = 220
const H = 52

function xy(i: number, score: number): { x: number; y: number } {
  const x = attempts.value.length <= 1 ? W / 2 : (i / (attempts.value.length - 1)) * W
  const y = H - 5 - (Math.max(0, Math.min(5, score)) / 5) * (H - 10)
  return { x, y }
}

const linePoints = computed(() =>
  attempts.value.map((a, i) => {
    const p = xy(i, a.overall_score ?? 0)
    return `${p.x},${p.y}`
  }).join(' '),
)

const dots = computed(() =>
  attempts.value.map((a, i) => xy(i, a.overall_score ?? 0)),
)

const trend = computed<{ delta: number; up: boolean; flat: boolean } | null>(() => {
  const scores = attempts.value.map((a) => a.overall_score ?? 0)
  if (scores.length < 2) return null
  const delta = scores[scores.length - 1] - scores[0]
  return { delta, up: delta > 0.05, flat: Math.abs(delta) <= 0.05 }
})

const latestDims = computed<Record<string, number>>(() => {
  const last = attempts.value[attempts.value.length - 1]
  const out: Record<string, number> = {}
  for (const [name, dim] of Object.entries(last?.dimension_scores || {})) {
    out[name] = dim.score
  }
  return out
})
</script>

<template>
  <div class="progress-card">
    <div class="pc-head">
      <div class="pc-title">
        {{ group.role_title }}<span v-if="group.company_name"> · {{ group.company_name }}</span>
      </div>
      <div class="pc-meta">{{ attempts.length }} 次面试</div>
    </div>
    <div class="pc-body">
      <div class="pc-chart">
        <div class="pc-label">总分趋势（/5）</div>
        <svg v-if="attempts.length > 1" :viewBox="`0 0 ${W} ${H}`" class="sparkline">
          <polyline :points="linePoints" class="spark-line" />
          <circle
            v-for="(d, i) in dots"
            :key="i"
            :cx="d.x"
            :cy="d.y"
            r="2.5"
            class="spark-dot"
          />
        </svg>
        <div v-else class="spark-empty">至少完成 2 次面试才能显示趋势</div>
        <div
          v-if="trend"
          class="pc-delta"
          :class="{ up: trend.up, down: !trend.up && !trend.flat }"
        >
          {{ trend.up ? '▲' : trend.flat ? '—' : '▼' }} {{ Math.abs(trend.delta).toFixed(1) }}
        </div>
      </div>
      <div class="pc-radar">
        <div class="pc-label">最新一轮维度</div>
        <RadarChart v-if="Object.keys(latestDims).length >= 3" :dimensions="latestDims" />
        <div v-else class="spark-empty">维度数据不足</div>
      </div>
    </div>
  </div>
</template>
