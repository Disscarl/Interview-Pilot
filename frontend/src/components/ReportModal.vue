<script setup lang="ts">
import { computed, onMounted } from 'vue'
import type { Report } from '../types'
import ReportBody from './ReportBody.vue'
import CoachBox from './CoachBox.vue'
import {
  reportCoach,
  reportCoachLoading,
  reportCoachError,
  generateReportCoach,
} from '../store'

const props = defineProps<{ report: Report }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const scoreText = computed(() =>
  props.report.overall_score != null ? props.report.overall_score.toFixed(1) : '?',
)

// 面试一结束就自动生成教练复盘（服务端缓存；失败可手动重试）。
onMounted(() => {
  void generateReportCoach()
})
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal">
      <h2>📊 面试评估报告</h2>
      <div class="score-big">{{ scoreText }} <span class="score-unit">/ 5.0</span></div>
      <ReportBody :report="report" />

      <div class="section-title">🎓 教练复盘</div>
      <div v-if="reportCoachError && !reportCoach" class="coach-error">
        生成失败：{{ reportCoachError }}
      </div>
      <CoachBox :coach="reportCoach" :loading="reportCoachLoading" @generate="() => generateReportCoach()" />

      <button @click="emit('close')">关闭</button>
    </div>
  </div>
</template>
