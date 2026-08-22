<script setup lang="ts">
import { ref } from 'vue'
import { authLogin, authRegister, authStatus, authStatusError } from '../store'

const username = ref('')
const password = ref('')
</script>

<template>
  <div id="auth-view">
    <div class="home-hero">
      <div class="logo">🎯 <span>Interview Pilot</span></div>
      <p class="tagline">登录后开始你的 AI 模拟面试</p>
    </div>
    <div class="jd-card auth-card">
      <input v-model="username" type="text" placeholder="用户名" autocomplete="username" />
      <input
        v-model="password"
        type="password"
        placeholder="密码"
        autocomplete="current-password"
        @keydown.enter="authLogin(username, password)"
      />
      <div class="auth-row">
        <button class="btn-primary" @click="authLogin(username, password)">登录</button>
        <button class="btn-ghost" @click="authRegister(username, password)">注册</button>
      </div>
      <div class="auth-status" :class="{ error: authStatusError }">{{ authStatus }}</div>
    </div>
  </div>
</template>
