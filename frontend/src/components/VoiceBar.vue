<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import type { ChatMessage } from '../types'
import { getToken } from '../api'
import { playVoiceUrl } from '../store'
import { fmtDur } from '../utils'

const props = defineProps<{ message: ChatMessage }>()

const playing = ref(false)
const progress = ref(0)
const showTranscript = ref(false)
let audio: HTMLAudioElement | null = null

function stop(): void {
  if (audio) {
    try {
      audio.pause()
    } catch {
      /* ignore */
    }
    audio = null
  }
  playing.value = false
}

function togglePlay(): void {
  const src = props.message.audio_url
  if (!src) return
  if (audio) {
    if (audio.paused) {
      audio.play().catch(() => {
        playing.value = false
      })
    } else {
      audio.pause()
    }
    return
  }
  const url =
    src.startsWith('blob:') || src.startsWith('data:')
      ? src
      : src + (src.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(getToken())
  const a = playVoiceUrl(url)
  if (!a) return
  a.addEventListener('timeupdate', () => {
    if (a.duration) progress.value = (a.currentTime / a.duration) * 100
  })
  a.addEventListener('play', () => {
    playing.value = true
  })
  a.addEventListener('pause', () => {
    playing.value = false
  })
  a.addEventListener('ended', () => {
    playing.value = false
    progress.value = 0
  })
  a.play().catch(() => {
    playing.value = false
  })
  audio = a
}

onBeforeUnmount(stop)
</script>

<template>
  <div class="bubble voice-bubble">
    <button class="vplay" @click="togglePlay">{{ playing ? '⏸' : '▶' }}</button>
    <div class="vbar"><div class="vprogress" :style="{ width: progress + '%' }"></div></div>
    <span class="vdur">{{ fmtDur(message.audio_duration || 0) }}</span>
    <span v-if="message.status" class="vstatus">{{ message.status }}</span>
  </div>
  <button
    class="voice-toggle-text"
    :disabled="!!message.pending"
    @click="showTranscript = !showTranscript"
  >
    转文字
  </button>
  <div v-show="showTranscript" class="voice-transcript">{{ message.transcript }}</div>
</template>
