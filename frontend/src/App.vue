<script setup lang="ts">
import { view, report, closeReport } from './store'
import AuthView from './views/AuthView.vue'
import HomeView from './views/HomeView.vue'
import InterviewView from './views/InterviewView.vue'
import HistoryView from './views/HistoryView.vue'
import ReportModal from './components/ReportModal.vue'
</script>

<template>
  <AuthView v-if="view === 'auth'" />
  <HomeView v-else-if="view === 'home'" />
  <InterviewView v-else-if="view === 'interview'" />
  <HistoryView v-else-if="view === 'history'" />
  <ReportModal v-if="report" :report="report" @close="closeReport()" />
</template>
