<script setup lang="ts">
import { ref } from 'vue'
import {
  logout,
  resumeName,
  resumeState,
  uploadResume,
  jdText,
  jdCompany,
  jdStatus,
  jdLoading,
  analyzeJd,
  plan,
  startInterview,
  openHistory,
} from '../store'
import VoiceSettings from '../components/VoiceSettings.vue'

const fileInput = ref<HTMLInputElement | null>(null)

function pickFile(): void {
  fileInput.value?.click()
}

function onFileChange(e: Event): void {
  const input = e.target as HTMLInputElement
  const file = input.files && input.files[0]
  if (file) void uploadResume(file)
  input.value = ''
}
</script>

<template>
  <div id="home-view">
    <div class="home-hero">
      <div class="logo">🎯 <span>Interview Pilot</span></div>
      <p class="tagline">
        AI 模拟面试 · 覆盖各行各业 · 根据 JD 定制面试计划 · 自适应追问 · 自动评估
      </p>
      <button class="logout-btn" @click="logout()">退出登录</button>
    </div>

    <div class="jd-card">
      <h2>从 JD 生成定制面试</h2>
      <p class="sub">上传简历并粘贴岗位 JD（建议完整 JD）即可生成面试；公司介绍选填。</p>

      <label class="jd-label">简历上传 <span class="opt">（必填，支持 PDF / Word）</span></label>
      <div class="resume-row">
        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.docx,.doc"
          hidden
          @change="onFileChange"
        />
        <button type="button" class="btn-ghost" @click="pickFile">选择简历文件</button>
        <span class="resume-name" :class="resumeState">{{ resumeName }}</span>
      </div>

      <label class="jd-label"
        >岗位 JD / 职位名 <span class="opt">（必填，建议粘贴完整 JD）</span></label
      >
      <textarea
        v-model="jdText"
        placeholder="建议粘贴完整 JD（公司介绍、岗位职责、任职要求…），面试效果更好；没有完整 JD 时，至少填写职位名（如：游戏客户端开发工程师）"
      ></textarea>

      <label class="jd-label">公司介绍 <span class="opt">（选填）</span></label>
      <textarea
        v-model="jdCompany"
        class="jd-company"
        placeholder="选填：公司名称 / 简介 / 主营业务"
      ></textarea>

      <button class="btn-primary" :disabled="jdLoading" @click="analyzeJd()">
        {{ jdLoading ? '解析中…' : '解析并生成面试计划' }}
      </button>
      <div v-if="jdStatus" class="jd-status" :class="jdStatus.kind">{{ jdStatus.text }}</div>
    </div>

    <VoiceSettings />

    <div v-if="plan" class="plan-preview">
      <h2>📋 面试计划已生成</h2>
      <div class="plan-meta" v-if="plan.profile?.company_name">
        <b>公司</b>：{{ plan.profile.company_name }}<span v-if="plan.profile.company_type">（{{ plan.profile.company_type }}）</span>
      </div>
      <div class="plan-meta" v-if="plan.profile?.industry"><b>行业</b>：{{ plan.profile.industry }}</div>
      <div class="plan-meta" v-if="plan.profile?.role_title"><b>岗位</b>：{{ plan.profile.role_title }}</div>
      <div class="plan-meta" v-if="plan.plan?.summary">{{ plan.plan.summary }}</div>

      <template v-if="plan.plan?.focus_areas?.length">
        <div class="section-title">🎯 重点考查领域</div>
        <div>
          <span v-for="(f, i) in plan.plan.focus_areas" :key="i" class="chip">{{ f }}</span>
        </div>
      </template>

      <template v-if="plan.profile?.tech_stack?.length">
        <div class="section-title">🛠 技术栈</div>
        <div>
          <span v-for="(t, i) in plan.profile.tech_stack" :key="i" class="chip">{{ t }}</span>
        </div>
      </template>

      <template
        v-if="
          plan.profile?.company_research &&
          (plan.profile.company_research.business ||
            plan.profile.company_research.products?.length ||
            plan.profile.company_research.history_projects?.length)
        "
      >
        <div class="section-title">🏢 公司调研</div>
        <div class="plan-meta" v-if="plan.profile.company_research.business">
          <b>核心业务</b>：{{ plan.profile.company_research.business }}
        </div>
        <div class="plan-meta" v-if="plan.profile.company_research.products?.length">
          <b>代表产品</b>：{{ plan.profile.company_research.products.join('、') }}
        </div>
        <div class="plan-meta" v-if="plan.profile.company_research.history_projects?.length">
          <b>历史项目</b>：{{ plan.profile.company_research.history_projects.join('、') }}
        </div>
        <div class="plan-meta" v-if="plan.profile.company_research.market_position">
          <b>行业地位</b>：{{ plan.profile.company_research.market_position }}
        </div>
      </template>

      <template
        v-if="
          plan.candidate &&
          (plan.candidate.skills?.length ||
            plan.candidate.projects?.length ||
            plan.candidate.years_of_experience)
        "
      >
        <div class="section-title">👤 候选人画像（来自简历）</div>
        <div class="plan-meta" v-if="plan.candidate.years_of_experience">
          <b>工作年限</b>：{{ plan.candidate.years_of_experience }}
        </div>
        <div class="plan-meta" v-if="plan.candidate.skills?.length">
          <b>技能</b>：{{ plan.candidate.skills.join('、') }}
        </div>
        <div class="plan-meta" v-if="plan.candidate.projects?.length">
          <b>项目</b>：{{ plan.candidate.projects.join('；') }}
        </div>
        <div class="plan-meta" v-if="plan.candidate.work_history?.length">
          <b>工作经历</b>：{{ plan.candidate.work_history.join('；') }}
        </div>
      </template>

      <div class="section-title">📝 面试阶段</div>
      <div v-for="(s, i) in plan.plan?.stages || []" :key="i" class="plan-stage">
        <div class="stage-name">{{ s.name }}</div>
        <div class="stage-goal">{{ s.goal }}</div>
        <div v-if="s.focus?.length" class="stage-focus">关注：{{ s.focus.join('、') }}</div>
      </div>

      <button class="btn-primary" @click="startInterview()">开始面试</button>
    </div>

    <button class="history-fab" @click="openHistory()">📚 历史面试</button>
  </div>
</template>
