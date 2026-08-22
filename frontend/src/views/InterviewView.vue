<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import {
  backHome,
  phaseBadge,
  messages,
  inputText,
  inputHint,
  inputHintError,
  recording,
  toggleRecording,
  cancelRecording,
  sendAnswer,
  endInterview,
  sendDisabled,
  endDisabled,
  inputDisabled,
  micDisabled,
  uiState,
} from '../store'
import MessageBubble from '../components/MessageBubble.vue'

const chatEl = ref<HTMLElement | null>(null)
const textareaEl = ref<HTMLTextAreaElement | null>(null)

function scrollToBottom(): void {
  void nextTick(() => {
    if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
  })
}

watch(messages, scrollToBottom, { deep: true })

watch(uiState, (s) => {
  if (s === 'active') {
    void nextTick(() => textareaEl.value?.focus())
  }
})

function onInput(): void {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}
</script>

<template>
  <div id="interview-view">
    <div class="topbar">
      <button class="back-btn" @click="backHome()">← 首页</button>
      <div class="logo"><span>🎯</span> Interview Pilot</div>
      <div class="topbar-right">
        <span class="badge"><span class="dot"></span>{{ phaseBadge }}</span>
      </div>
    </div>

    <div ref="chatEl" class="chat-container">
      <div class="chat-inner">
        <MessageBubble v-for="m in messages" :key="m.id" :message="m" />
      </div>
    </div>

    <div class="input-area">
      <div class="input-wrap">
        <button
          class="mic-btn"
          :class="{ recording }"
          :disabled="micDisabled()"
          title="语音输入（最长 5 分钟）"
          @click="toggleRecording()"
        >
          {{ recording ? '⏹' : '🎤' }}
        </button>
        <button v-if="recording" class="mic-cancel" @click="cancelRecording()">取消</button>
        <textarea
          ref="textareaEl"
          v-model="inputText"
          rows="1"
          placeholder="输入你的回答..."
          :disabled="inputDisabled()"
          @input="onInput"
          @keydown.enter.exact.prevent="sendAnswer()"
        ></textarea>
        <button class="send-btn" :disabled="sendDisabled()" @click="sendAnswer()">发送</button>
        <button class="secondary" :disabled="endDisabled()" @click="endInterview()">结束</button>
      </div>
      <div class="input-hint" :style="{ color: inputHintError ? '#ff9aab' : '' }">
        {{ inputHint }}
      </div>
    </div>
  </div>
</template>
