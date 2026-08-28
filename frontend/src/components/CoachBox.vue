<script setup lang="ts">
import type { CoachReport } from '../types'

defineProps<{
  coach?: CoachReport | null
  loading?: boolean
}>()

defineEmits<{ (e: 'generate'): void }>()
</script>

<template>
  <div v-if="coach" class="coach-box">
    <div class="coach-summary">💬 {{ coach.summary || '' }}</div>
    <div v-if="coach.weak_analysis?.length" class="coach-block">
      <div class="coach-h">薄弱点</div>
      <ul>
        <li v-for="(w, i) in coach.weak_analysis" :key="i">{{ w }}</li>
      </ul>
    </div>
    <div v-if="coach.study_plan?.length" class="coach-block">
      <div class="coach-h">学习计划</div>
      <ul>
        <li v-for="(p, i) in coach.study_plan" :key="i">
          <b>{{ p.action }}</b>
          <span v-if="p.why" class="coach-why">（{{ p.why }}）</span>
        </li>
      </ul>
    </div>
    <div v-if="coach.next_focus?.length" class="coach-block">
      <div class="coach-h">下次重点</div>
      <div>
        <span v-for="(f, i) in coach.next_focus" :key="i" class="chip">{{ f }}</span>
      </div>
    </div>
    <div v-if="coach.next_first_question" class="coach-next">
      下次首问：{{ coach.next_first_question }}
    </div>
  </div>
  <button v-else class="btn-ghost coach-btn" :disabled="loading" @click="$emit('generate')">
    {{ loading ? '生成中…' : '🎓 生成教练复盘' }}
  </button>
</template>
