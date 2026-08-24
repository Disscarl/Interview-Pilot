<script setup lang="ts">
// Dependency-free SVG radar chart for evaluation dimension scores (0-5).
import { computed } from 'vue'

const props = defineProps<{ dimensions: Record<string, number> }>()

const SIZE = 320
const CX = SIZE / 2
const CY = SIZE / 2
const RADIUS = 84
const LABEL_RATIO = 1.32

const entries = computed<{ label: string; score: number }[]>(() =>
  Object.entries(props.dimensions || {}).map(([label, score]) => ({
    label,
    score: Math.max(0, Math.min(5, Number(score) || 0)),
  })),
)

const n = computed(() => entries.value.length)
const show = computed(() => n.value >= 3)

function point(i: number, ratio: number): [number, number] {
  const angle = (-90 + (i * 360) / n.value) * (Math.PI / 180)
  return [CX + RADIUS * ratio * Math.cos(angle), CY + RADIUS * ratio * Math.sin(angle)]
}

const gridPolygons = computed(() =>
  [0.25, 0.5, 0.75, 1].map((lv) =>
    Array.from({ length: n.value }, (_, i) => point(i, lv).join(',')).join(' '),
  ),
)

const axisLines = computed(() =>
  Array.from({ length: n.value }, (_, i) => {
    const [x2, y2] = point(i, 1)
    return { x1: CX, y1: CY, x2, y2 }
  }),
)

const dataPoints = computed(() =>
  entries.value.map((e, i) => point(i, e.score / 5).join(',')).join(' '),
)

const dots = computed(() =>
  entries.value.map((e, i) => {
    const [x, y] = point(i, e.score / 5)
    return { x, y }
  }),
)

const labelPositions = computed(() =>
  entries.value.map((e, i) => {
    const [x, y] = point(i, LABEL_RATIO)
    return {
      label: e.label,
      x,
      y,
      anchor: x > CX + 8 ? 'start' : x < CX - 8 ? 'end' : 'middle',
    }
  }),
)
</script>

<template>
  <div v-if="show" class="radar-wrap">
    <svg :viewBox="`0 0 ${SIZE} ${SIZE}`" class="radar" role="img" aria-label="评估维度雷达图">
      <polygon
        v-for="(poly, idx) in gridPolygons"
        :key="idx"
        :points="poly"
        class="radar-grid"
      />
      <line
        v-for="(line, idx) in axisLines"
        :key="idx"
        :x1="line.x1"
        :y1="line.y1"
        :x2="line.x2"
        :y2="line.y2"
        class="radar-axis"
      />
      <polygon :points="dataPoints" class="radar-data" />
      <circle
        v-for="(d, i) in dots"
        :key="i"
        :cx="d.x"
        :cy="d.y"
        r="2.5"
        class="radar-dot"
      />
      <text
        v-for="(lp, i) in labelPositions"
        :key="i"
        :x="lp.x"
        :y="lp.y"
        :text-anchor="lp.anchor"
        dominant-baseline="central"
        class="radar-label"
      >
        {{ lp.label }}
      </text>
    </svg>
  </div>
  <p v-else class="dim-comment">维度数据不足，无法绘制雷达图</p>
</template>
