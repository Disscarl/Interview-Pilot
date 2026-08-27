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
          />
        </template>
      </template>

      <!-- 详情 -->
      <div v-else class="history-detail">
        <div class="hd-back">
          <button class="back-btn" @click="backToList()">← 返回</button>
          <button class="delete-btn" @click="deleteHistory(historyDetail.id)">删除</button>
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
