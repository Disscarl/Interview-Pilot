<script setup lang="ts">
import { computed } from 'vue'
import {
  showView,
  historyItems,
  historyDetail,
  historyLoading,
  historyError,
  viewHistoryDetail,
  backToList,
  deleteHistory,
} from '../store'
import type { ChatMessage } from '../types'
import MessageBubble from '../components/MessageBubble.vue'
import ReportBody from '../components/ReportBody.vue'

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
</script>

<template>
  <div id="history-view">
    <div class="topbar">
      <button class="back-btn" @click="goHome()">← 首页</button>
      <div class="logo"><span>📚</span> 历史面试</div>
    </div>

    <div class="history-container">
      <!-- List -->
      <div v-if="!historyDetail" id="history-list">
        <div v-if="historyLoading" class="history-empty">加载中…</div>
        <div v-else-if="historyError" class="history-empty">加载失败：{{ historyError }}</div>
        <div v-else-if="!historyItems.length" class="history-empty">
          还没有历史面试记录<br />完成一次面试后会自动保存到这里
        </div>
        <div
          v-for="it in historyItems"
          v-else
          :key="it.id"
          class="history-card"
          @click="viewHistoryDetail(it.id)"
        >
          <div class="hc-top">
            <span class="hc-role">{{ it.role_title || '面试' }}</span>
            <span class="hc-score">{{ scoreText(it.overall_score) }}</span>
          </div>
          <div class="hc-meta">{{ it.company_name || '未知公司' }} · {{ it.created_at || '' }}</div>
        </div>
      </div>

      <!-- Detail -->
      <div v-else-if="historyDetail" class="history-detail">
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
