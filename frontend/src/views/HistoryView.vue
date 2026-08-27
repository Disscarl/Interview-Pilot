<script setup lang="ts">
import { computed } from 'vue'
import {
  showView,
  historyDetail,
  historyLoading,
  historyError,
  progressGroups,
  viewHistoryDetail,
  backToList,
  deleteHistory,
  reInterview,
  generateCoach,
  coachLoading,
} from '../store'
import type { ChatMessage, ProgressGroup } from '../types'
import MessageBubble from '../components/MessageBubble.vue'
import ReportBody from '../components/ReportBody.vue'
import ProgressCard from '../components/ProgressCard.vue'

function goHome(): void {
  showView('home')
}

function scoreText(score: number | null | undefined): string {
  return score != null ? score.toFixed(1) : '—'
}

const detailMessages = computed<ChatMessage[]>(() =>
  (historyDetail.value?.messages || []).map((m, i) => ({
    id: i,
    role: m.role,
    content: m.content,
    phase: m.phase,
    audio_url: m.audio_url,
    audio_duration: m.audio_duration,
    transcript: m.audio_url ? m.content : undefined,
  })),
)

// 按岗位分组的卡片，最近活跃的岗位排最前。
const orderedGroups = computed<ProgressGroup[]>(() =>
  [...progressGroups.value].sort((a, b) => {
    const lastA = a.attempts[a.attempts.length - 1]?.created_at || ''
    const lastB = b.attempts[b.attempts.length - 1]?.created_at || ''
    return lastB.localeCompare(lastA)
  }),
)
</script>

<template>
  <div id="history-view">
    <div class="topbar">
      <button class="back-btn" @click="goHome()">← 首页</button>
      <div class="logo"><span>📚</span> 历史面试</div>
    </div>

    <div class="history-container">
      <!-- 分组列表：每个岗位一张卡片（趋势概览 + 历次记录） -->
      <template v-if="!historyDetail">
        <div v-if="historyLoading" class="history-empty">加载中…</div>
        <div v-else-if="historyError" class="history-empty">加载失败：{{ historyError }}</div>
        <div v-else-if="!orderedGroups.length" class="history-empty">
          还没有历史面试记录<br />完成一次面试后会自动保存到这里
        </div>
        <template v-else>
          <div class="history-subtitle">按岗位分组 · 点击记录查看详情</div>
          <ProgressCard
            v-for="(g, i) in orderedGroups"
            :key="g.role_title + '|' + g.company_name"
            :group="g"
            @open="viewHistoryDetail"
            @reinterview="reInterview"
          />
        </template>
      </template>

      <!-- 详情 -->
      <div v-else class="history-detail">
        <div class="hd-back">
          <button class="back-btn" @click="backToList()">← 返回</button>
          <div class="hd-actions">
            <button class="re-btn" @click="reInterview(historyDetail.id)">🔄 再来一次</button>
            <button class="delete-btn" @click="deleteHistory(historyDetail.id)">删除</button>
          </div>
        </div>
        <div class="hd-head">
          <div class="hd-left">
            <div class="hd-role">{{ historyDetail.role_title || '面试' }}</div>
            <div class="hd-meta">
              <span>{{ historyDetail.company_name || '未知公司' }}</span>
              <span>{{ historyDetail.created_at || '' }}</span>
            </div>
          </div>
          <div class="hd-score">
            {{ scoreText(historyDetail.overall_score) }}<span class="hd-score-total"> / 5</span>
          </div>
        </div>
        <div class="hd-divider"></div>

        <div class="section-title">📊 评估报告</div>
        <ReportBody v-if="historyDetail.report" :report="historyDetail.report" />

        <div class="section-title">🎓 教练复盘</div>
        <template v-if="historyDetail.coach">
          <div class="coach-box">
            <div class="coach-summary">💬 {{ historyDetail.coach.summary || '' }}</div>
            <div v-if="historyDetail.coach.weak_analysis?.length" class="coach-block">
              <div class="coach-h">薄弱点</div>
              <ul>
                <li v-for="(w, i) in historyDetail.coach.weak_analysis" :key="i">{{ w }}</li>
              </ul>
            </div>
            <div v-if="historyDetail.coach.study_plan?.length" class="coach-block">
              <div class="coach-h">学习计划</div>
              <ul>
                <li v-for="(p, i) in historyDetail.coach.study_plan" :key="i">
                  <b>{{ p.action }}</b>
                  <span v-if="p.why" class="coach-why">（{{ p.why }}）</span>
                </li>
              </ul>
            </div>
            <div v-if="historyDetail.coach.next_focus?.length" class="coach-block">
              <div class="coach-h">下次重点</div>
              <div>
                <span v-for="(f, i) in historyDetail.coach.next_focus" :key="i" class="chip">{{ f }}</span>
              </div>
            </div>
            <div v-if="historyDetail.coach.next_first_question" class="coach-next">
              下次首问：{{ historyDetail.coach.next_first_question }}
            </div>
          </div>
        </template>
        <template v-else>
          <button
            class="btn-ghost coach-btn"
            :disabled="coachLoading"
            @click="generateCoach(historyDetail.id)"
          >
            {{ coachLoading ? '生成中…' : '🎓 生成教练复盘' }}
          </button>
        </template>

        <div class="section-title">💬 对话记录</div>
        <div class="history-transcript">
          <template v-if="detailMessages.length">
            <MessageBubble v-for="m in detailMessages" :key="m.id" :message="m" />
          </template>
          <div v-else class="history-empty">无对话</div>
        </div>
      </div>
    </div>
  </div>
</template>
