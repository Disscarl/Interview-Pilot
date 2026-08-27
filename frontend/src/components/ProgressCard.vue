<script setup lang="ts">
import { computed } from 'vue'
import type { ProgressGroup } from '../types'
import RadarChart from './RadarChart.vue'

const props = defineProps<{ group: ProgressGroup }>()
const emit = defineEmits<{ (e: 'open', id: string): void; (e: 'reinterview', id: string): void }>()

// Backend returns attempts oldest-first; records display newest-first.
const attemptsDesc = computed(() =>
  [...props.group.attempts].sort((a, b) =>
    (b.created_at || '').localeCompare(a.created_at || ''),
  ),
)

const latestId = computed(() => attemptsDesc.value[0]?.id ?? '')

const attemptsAsc = computed(() => props.group.attempts)

const W = 220
const H = 52

function xy(i: number, score: number): { x: number; y: number } {
  const x = attemptsAsc.value.length <= 1 ? W / 2 : (i / (attemptsAsc.value.length - 1)) * W
  const y = H - 5 - (Math.max(0, Math.min(5, score)) / 5) * (H - 10)
  return { x, y }
}

const linePoints = computed(() =>
  attemptsAsc.value.map((a, i) => {
    const p = xy(i, a.overall_score ?? 0)
    return `${p.x},${p.y}`
  }).join(' '),
)

const dots = computed(() =>
  attemptsAsc.value.map((a, i) => xy(i, a.overall_score ?? 0)),
)

const trend = computed<{ delta: number; up: boolean; flat: boolean } | null>(() => {
  const scores = attemptsAsc.value.map((a) => a.overall_score ?? 0)
  if (scores.length < 2) return null
  const delta = scores[scores.length - 1] - scores[0]
  return { delta, up: delta > 0.05, flat: Math.abs(delta) <= 0.05 }
})

const latestDims = computed<Record<string, number>>(() => {
  const last = attemptsAsc.value[attemptsAsc.value.length - 1]
  const out: Record<string, number> = {}
  for (const [name, dim] of Object.entries(last?.dimension_scores || {})) {
    out[name] = dim.score
  }
  return out
})

// 趋势线需要 ≥2 次才有对比意义；雷达图（最新一轮维度）第一次面试即可展示。
const showTrend = computed(() => attemptsDesc.value.length >= 2)
const showAggregate = computed(
  () => showTrend.value || Object.keys(latestDims.value).length >= 3,
)

function scoreText(score: number | null | undefined): string {
  return score != null ? score.toFixed(1) : '—'
}
</script>

<template>
  <div class="progress-card">
    <!-- 分组头：岗位 + 次数 + 总分变化 + 重考 -->
    <div class="pc-head">
      <div class="pc-title">
        {{ group.role_title }}<span v-if="group.company_name"> · {{ group.company_name }}</span>
      </div>
      <div class="pc-head-right">
        <div class="pc-meta">
          <span>{{ attemptsDesc.length }} 次面试</span>
          <span
            v-if="trend"
            class="pc-delta"
            :class="{ up: trend.up, down: !trend.up && !trend.flat }"
          >
            {{ trend.up ? '▲' : trend.flat ? '—' : '▼' }} {{ Math.abs(trend.delta).toFixed(1) }}
          </span>
        </div>
        <button class="pc-re-btn" @click="emit('reinterview', latestId)">🔄 重新面试</button>
      </div>
    </div>

    <!-- 概览：雷达图（≥1 次即显示）；趋势线需 ≥2 次才有对比意义 -->
    <div v-if="showAggregate" class="pc-body">
      <div v-if="showTrend" class="pc-chart">
        <div class="pc-label">总分趋势（/5）</div>
        <svg :viewBox="`0 0 ${W} ${H}`" class="sparkline">
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
      </div>
      <div class="pc-radar">
        <div class="pc-label">最新一轮维度</div>
        <RadarChart v-if="Object.keys(latestDims).length >= 3" :dimensions="latestDims" />
        <div v-else class="spark-empty">维度数据不足</div>
      </div>
    </div>

    <!-- 该岗位的历次面试记录 -->
    <div class="pc-records">
      <div
        v-for="a in attemptsDesc"
        :key="a.id"
        class="pc-record"
        @click="emit('open', a.id)"
      >
        <span class="pr-date">{{ a.created_at || '' }}</span>
        <span class="pr-score">{{ scoreText(a.overall_score) }}</span>
      </div>
    </div>
  </div>
</template>
