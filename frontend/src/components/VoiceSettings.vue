<script setup lang="ts">
import { TTS_VOICES, ttsVoice, ttsSpeed, onVoiceChange, onRateChange, previewVoice, voicePreviewLoading, voiceStatus, voiceStatusError } from '../store'
</script>

<template>
  <div class="jd-card voice-settings-card">
    <h2>🎙️ 面试官设置</h2>
    <p class="sub">面试前设置面试官语音的音色和语速；进入面试后，每条面试官消息可点「🔊 朗读」手动播报。</p>
    <div class="vs-row">
      <label for="voice-select">声音</label>
      <select id="voice-select" v-model="ttsVoice" @change="onVoiceChange()">
        <option v-for="v in TTS_VOICES" :key="v.id" :value="v.id">{{ v.label }}</option>
      </select>
    </div>
    <div class="vs-row">
      <label for="rate-select">语速</label>
      <select id="rate-select" v-model="ttsSpeed" @change="onRateChange()">
        <option value="30">慢速</option>
        <option value="40">稍慢</option>
        <option value="50">正常</option>
        <option value="60">稍快</option>
        <option value="70">快速</option>
      </select>
    </div>
    <div class="vs-actions">
      <button class="vs-preview" :disabled="voicePreviewLoading" @click="previewVoice()">
        {{ voicePreviewLoading ? '合成中…' : '试听' }}
      </button>
    </div>
    <div class="voice-status" :style="{ color: voiceStatusError ? '#ff9aab' : '' }">
      {{ voiceStatus }}
    </div>
  </div>
</template>
