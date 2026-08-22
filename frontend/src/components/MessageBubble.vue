<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessage } from '../types'
import { phaseLabel } from '../utils'
import { playMessageTts } from '../store'
import VoiceBar from './VoiceBar.vue'

const props = defineProps<{ message: ChatMessage }>()

const isCandidate = computed(() => props.message.role === 'candidate')
const phaseChip = computed(() => phaseLabel(props.message.phase))

function playTts(): void {
  void playMessageTts(props.message.content || '')
}
</script>

<template>
  <div
    class="message"
    :class="[isCandidate ? 'you' : 'interviewer', { typing: message.typing }]"
  >
    <div class="avatar">{{ isCandidate ? '👤' : '🤖' }}</div>
    <div class="msg-body">
      <div v-if="phaseChip" class="msg-meta">
        <span class="phase-chip">{{ phaseChip }}</span>
      </div>

      <VoiceBar v-if="message.audio_url" :message="message" />

      <template v-else>
        <div class="bubble">
          <template v-if="message.typing">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </template>
          <template v-else>{{ message.content }}</template>
        </div>
        <button
          v-if="!isCandidate && !message.typing && message.content"
          class="msg-play-btn"
          @click="playTts"
        >
          🔊 朗读
        </button>
      </template>
    </div>
  </div>
</template>
