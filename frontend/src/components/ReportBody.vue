<script setup lang="ts">
import type { Report } from '../types'

const props = defineProps<{ report: Report }>()

function pct(score: number | undefined): number {
  const s = Number(score || 0)
  return Math.max(0, Math.min(100, (s / 5) * 100))
}

function dimEntries(): [string, { score: number; comment?: string }][] {
  return Object.entries(props.report.dimension_scores || {})
}
</script>

<template>
  <p class="report-summary">{{ report.summary || '' }}</p>

  <template v-for="[name, dim] in dimEntries()" :key="name">
    <div class="dimension-bar">
      <span class="dim-label">{{ name }}</span>
      <div class="dim-track">
        <div class="dim-fill" :style="{ width: pct(dim.score) + '%' }"></div>
      </div>
      <span class="dim-score">{{ dim.score }}/5</span>
    </div>
    <div class="dim-comment">{{ dim.comment || '' }}</div>
  </template>

  <div class="report-section">
    <h3>🌟 亮点</h3>
    <ul>
      <li v-for="(h, i) in report.highlights || []" :key="i">✅ {{ h }}</li>
      <li v-if="!(report.highlights && report.highlights.length)">暂无</li>
    </ul>
  </div>

  <div class="report-section">
    <h3>🎯 薄弱点</h3>
    <ul>
      <li v-for="(w, i) in report.weak_points || []" :key="i">
        ⚠️ <b>{{ w.area }}</b>: {{ w.description }}<br /><i>建议: {{ w.suggestion }}</i>
      </li>
      <li v-if="!(report.weak_points && report.weak_points.length)">暂无</li>
    </ul>
  </div>

  <div class="report-section">
    <h3>📚 推荐学习方向</h3>
    <ul>
      <li v-for="(t, i) in report.recommended_topics || []" :key="i">📚 {{ t }}</li>
      <li v-if="!(report.recommended_topics && report.recommended_topics.length)">暂无</li>
    </ul>
  </div>
</template>
