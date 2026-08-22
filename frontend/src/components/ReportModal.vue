<script setup lang="ts">
import { computed } from 'vue'
import type { Report } from '../types'
import ReportBody from './ReportBody.vue'

const props = defineProps<{ report: Report }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const scoreText = computed(() =>
  props.report.overall_score != null ? props.report.overall_score.toFixed(1) : '?',
)
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal">
      <h2>📊 面试评估报告</h2>
      <div class="score-big">{{ scoreText }} <span class="score-unit">/ 5.0</span></div>
      <ReportBody :report="report" />
      <button @click="emit('close')">关闭</button>
    </div>
  </div>
</template>
