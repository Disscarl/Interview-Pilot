// Global reactive store (single module, no cross-import cycles).
// Holds auth/view routing, JD analysis, WebSocket interview streaming,
// TTS playback, voice recording (STT), history, and the report modal.
import { ref } from 'vue'
import type {
  CandidateVoiceData,
  ChatMessage,
  CoachReport,
  HistoryRecord,
  JdAnalysis,
  ProgressGroup,
  Report,
  TranscriptMessage,
  TtsVoice,
  ViewName,
  WsIncoming,
} from './types'
import * as api from './api'
import { fmtDur, phaseLabel } from './utils'

// ── View routing ──────────────────────────────────────────
export const view = ref<ViewName>(api.authToken.value ? 'home' : 'auth')

export function showView(name: ViewName): void {
  view.value = name
}

// ── Auth ──────────────────────────────────────────────────
export const authStatus = ref('')
export const authStatusError = ref(false)

function setAuthStatus(msg: string, isError = false): void {
  authStatus.value = msg || ''
  authStatusError.value = isError
}

export async function authLogin(username: string, password: string): Promise<void> {
  if (!username || !password) {
    setAuthStatus('请输入用户名和密码', true)
    return
  }
  try {
    const token = await api.login(username, password)
    api.setToken(token)
    enterApp()
  } catch (e) {
    setAuthStatus(e instanceof Error ? e.message : '登录失败', true)
  }
}

export async function authRegister(username: string, password: string): Promise<void> {
  if (!username || !password) {
    setAuthStatus('请输入用户名和密码', true)
    return
  }
  try {
    const token = await api.register(username, password)
    api.setToken(token)
    enterApp()
  } catch (e) {
    setAuthStatus(e instanceof Error ? e.message : '注册失败', true)
  }
}

function enterApp(): void {
  setAuthStatus('')
  showView('home')
}

function resetInterviewState(): void {
  stopTtsAudio()
  if (recording.value) cancelRecording()
  closedByUser = true
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  clearCreateRetry()
  createSentForSocket = null
  if (ws) {
    ws.onclose = null
    try {
      ws.close()
    } catch {
      /* ignore */
    }
  }
  ws = null
  connected.value = false
  currentJd = null
  plan.value = null
  streamId = null
  pendingVoiceMsgId.value = null
  messages.value = []
  inputText.value = ''
  clearInputHint()
  setPhaseBadge(null)
  lastReportId.value = null
  reportCoach.value = null
  reportCoachError.value = ''
}

export function logout(): void {
  api.setToken('')
  resetInterviewState()
  // Never leak the previous user's resume/JD into the next login.
  resumeText = null
  jdText.value = ''
  jdCompany.value = ''
  resumeName.value = '未选择文件'
  resumeState.value = ''
  showView('auth')
}

// ── JD analysis state ─────────────────────────────────────
export const resumeName = ref('未选择文件')
export const resumeState = ref('') // '' | 'ok' | 'error'
let resumeText: string | null = null
export const jdText = ref('')
export const jdCompany = ref('')
export const jdStatus = ref<{ text: string; kind: 'error' | 'info' } | null>(null)
export const jdLoading = ref(false)
export const plan = ref<JdAnalysis | null>(null)
let currentJd: JdAnalysis | null = null

function setJdStatus(text: string, kind: 'error' | 'info'): void {
  jdStatus.value = { text, kind }
}

export async function uploadResume(file: File): Promise<void> {
  resumeName.value = '读取中：' + file.name
  resumeState.value = ''
  try {
    const dataBase64 = await readFileAsBase64(file)
    const { text, truncated } = await api.extractResume(file.name, dataBase64)
    resumeText = text
    resumeName.value =
      '已读取：' + file.name + (truncated ? '（简历较长，已截取前 20000 字）' : '')
    resumeState.value = 'ok'
  } catch (e) {
    resumeText = null
    resumeName.value = e instanceof Error ? e.message : '上传失败：' + file.name
    resumeState.value = 'error'
  }
}

export async function analyzeJd(): Promise<void> {
  if (!resumeText) {
    setJdStatus('请先上传简历（必填）', 'error')
    return
  }
  const text = jdText.value.trim()
  if (!text) {
    setJdStatus('请先填写岗位 JD 或职位名', 'error')
    return
  }
  setJdStatus('正在解析并生成面试计划…（约需几秒）', 'info')
  jdLoading.value = true
  try {
    const data = await api.analyzeJd({
      text,
      company: jdCompany.value.trim() || undefined,
      resume_text: resumeText,
    })
    currentJd = data
    plan.value = data
    jdStatus.value = null
  } catch (e) {
    setJdStatus(e instanceof Error ? e.message : '解析失败，请重试', 'error')
  } finally {
    jdLoading.value = false
  }
}

// ── Voice (TTS) ───────────────────────────────────────────
export const TTS_VOICES: TtsVoice[] = [
  { id: 'x5_lingxiaotang_flow', label: '聆小糖 · 女声（默认）' },
  { id: 'x5_lingyuzhao_flow', label: '聆玉昭 · 女声' },
  { id: 'x6_lingxiaoxuan_pro', label: '聆小璇 · 女声' },
  { id: 'x6_lingxiaoyue_pro', label: '聆小玥 · 女声' },
  { id: 'x6_lingyuyan_pro', label: '聆玉言 · 女声' },
  { id: 'x7_yaxi_pro', label: '雅夕 · 女声' },
  { id: 'x6_lingfeiyi_pro', label: '聆飞逸 · 男声' },
  { id: 'x6_ruyadashu_pro', label: '儒雅大叔 · 男声' },
  { id: 'x7_langxiao_pro', label: '朗霄 · 男声' },
]

export const ttsVoice = ref(localStorage.getItem('tts_voice') || 'x5_lingxiaotang_flow')
export const ttsSpeed = ref(localStorage.getItem('tts_speed') || '50')
export const voiceStatus = ref('')
export const voiceStatusError = ref(false)
export const voicePreviewLoading = ref(false)

export function onVoiceChange(): void {
  localStorage.setItem('tts_voice', ttsVoice.value)
}

export function onRateChange(): void {
  localStorage.setItem('tts_speed', ttsSpeed.value)
}

function setVoiceStatus(msg: string, isError = false): void {
  voiceStatus.value = msg || ''
  voiceStatusError.value = isError
}

let currentAudio: HTMLAudioElement | null = null

function playTtsBase64(b64: string): void {
  stopTtsAudio()
  currentAudio = new Audio('data:audio/mpeg;base64,' + b64)
  currentAudio.play().catch((e) => console.warn('TTS play blocked:', e))
}

export function stopTtsAudio(): void {
  if (currentAudio) {
    try {
      currentAudio.pause()
    } catch {
      /* ignore */
    }
    currentAudio = null
  }
}

// ── Voice-bar playback (coordinated with TTS) ─────────────
let activeVoiceAudio: HTMLAudioElement | null = null

export function stopVoicePlayback(): void {
  if (activeVoiceAudio) {
    try {
      activeVoiceAudio.pause()
    } catch {
      /* ignore */
    }
    activeVoiceAudio = null
  }
}

export function playVoiceUrl(url: string): HTMLAudioElement | null {
  // Only one thing plays at a time: stop any TTS and any other voice bar.
  stopTtsAudio()
  stopVoicePlayback()
  try {
    activeVoiceAudio = new Audio(url)
  } catch {
    return null
  }
  return activeVoiceAudio
}

export async function playMessageTts(text: string): Promise<void> {
  if (!text || !text.trim()) return
  try {
    const b64 = await api.ttsPreview(text, ttsVoice.value, Number(ttsSpeed.value))
    playTtsBase64(b64)
  } catch (e) {
    showInputHint('语音合成失败：' + (e instanceof Error ? e.message : ''), true)
  }
}

export async function previewVoice(): Promise<void> {
  voicePreviewLoading.value = true
  setVoiceStatus('')
  try {
    const b64 = await api.ttsPreview(
      '你好，我是本次模拟面试的面试官，这是语音播报效果。',
      ttsVoice.value,
      Number(ttsSpeed.value),
    )
    playTtsBase64(b64)
  } catch (e) {
    setVoiceStatus('试听失败：' + (e instanceof Error ? e.message : ''), true)
  } finally {
    voicePreviewLoading.value = false
  }
}

// ── Interview (WebSocket + streaming) ─────────────────────
export const messages = ref<ChatMessage[]>([])
export const connected = ref(false)
export const uiState = ref<'pre' | 'active' | 'done'>('pre')
export const phaseBadge = ref('准备中')
/** Raw phase key of the current stage ('' | intro | warm_up | … | closing | done). */
export const currentPhase = ref<string | null>(null)
export const inputText = ref('')
export const inputHint = ref('Enter 发送 · Shift+Enter 换行 · 🎤 语音输入')
export const inputHintError = ref(false)

let sessionId: string | null = null
let ws: WebSocket | null = null
let closedByUser = false
let reconnectAttempts = 0
let reconnectTimer: number | null = null
let shouldResume = false
let streamId: number | null = null
let createRetryTimer: number | null = null
let createSentForSocket: WebSocket | null = null
const pendingVoiceMsgId = ref<number | null>(null)
let nextMsgId = 1

export const streaming = ref(false)
export const recording = ref(false)

export const micDisabled = () => uiState.value !== 'active' || pendingVoiceMsgId.value !== null
export const sendDisabled = () =>
  uiState.value !== 'active' || !connected.value || streaming.value
export const endDisabled = () => uiState.value !== 'active' || !connected.value
export const inputDisabled = () => uiState.value !== 'active'

function setPhaseBadge(phase: string | null): void {
  currentPhase.value = phase
  phaseBadge.value =
    phase === 'done'
      ? '完成'
      : phase === null
        ? '准备中'
        : phaseLabel(phase) || '准备中'
}

function setUIState(state: 'pre' | 'active' | 'done'): void {
  uiState.value = state
}

export function showInputHint(msg: string, isError = false): void {
  inputHint.value = msg
  inputHintError.value = isError
}

export function clearInputHint(): void {
  inputHint.value = 'Enter 发送 · Shift+Enter 换行 · 🎤 语音输入'
  inputHintError.value = false
}

function addMessage(role: ChatMessage['role'], content: string, phase?: string): void {
  messages.value.push({ id: nextMsgId++, role, content, phase })
}

function addTyping(): void {
  if (streamId !== null) return
  const id = nextMsgId++
  messages.value.push({ id, role: 'interviewer', content: '', typing: true })
  streamId = id
  streaming.value = true
}

function removeTyping(): void {
  if (streamId !== null) {
    const msg = messages.value.find((m) => m.id === streamId)
    if (msg && msg.typing) {
      messages.value = messages.value.filter((m) => m.id !== streamId)
    }
  }
  streamId = null
  streaming.value = false
}

function appendStreamToken(token: string): void {
  if (streamId === null && !streaming.value) return // stale token — ignore
  let msg = streamId !== null ? messages.value.find((m) => m.id === streamId) : undefined
  if (!msg) {
    const id = nextMsgId++
    msg = { id, role: 'interviewer', content: '', typing: false }
    messages.value.push(msg)
    streamId = id
  } else if (msg.typing) {
    msg.typing = false
    msg.content = ''
  }
  msg.content = (msg.content || '') + token
  streaming.value = true
}

function endStream(phase?: string): void {
  if (streamId !== null) {
    const msg = messages.value.find((m) => m.id === streamId)
    if (msg) {
      if (msg.typing) {
        messages.value = messages.value.filter((m) => m.id !== streamId)
      } else {
        msg.phase = phase
      }
    }
  }
  streamId = null
  streaming.value = false
  if (phase) setPhaseBadge(phase)
  if (uiState.value !== 'done') setUIState('active')
}

function connectWs(): void {
  if (!sessionId) {
    sessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
  }
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${location.host}/ws/${sessionId}?token=${encodeURIComponent(api.getToken())}`

  ws = new WebSocket(url)

  ws.onopen = () => {
    connected.value = true
    reconnectAttempts = 0
    // Fresh socket: allow one create message. Do NOT clear the retry timer
    // here — startInterview's sendCreate relies on it to fire after open.
    createSentForSocket = null
    if (shouldResume) {
      shouldResume = false
      sendCreate(true)
    }
  }

  ws.onmessage = (ev) => {
    let data: WsIncoming
    try {
      data = JSON.parse(ev.data) as WsIncoming
    } catch {
      return
    }
    handleWsMessage(data)
  }

  ws.onclose = () => {
    connected.value = false
    clearCreateRetry()
    if (!closedByUser) scheduleReconnect()
  }

  ws.onerror = (err) => {
    console.error('WebSocket error:', err)
  }
}

function handleWsMessage(data: WsIncoming): void {
  switch (data.type) {
    case 'created':
      setPhaseBadge('intro')
      break

    case 'resume':
      renderMessages(data.messages)
      setPhaseBadge(data.phase)
      setUIState('active')
      break

    case 'message':
      if (streaming.value) endStream()
      removeTyping()
      addMessage(data.role, data.content, data.phase)
      setPhaseBadge(data.phase || null)
      if (uiState.value !== 'done') setUIState('active')
      break

    case 'thinking':
      addTyping()
      break

    case 'stream_token':
      appendStreamToken(data.content)
      break

    case 'stream_end':
      endStream(data.phase)
      break

    case 'candidate_voice':
      handleCandidateVoice(data)
      break

    case 'interview_end':
      stopTtsAudio()
      removeTyping()
      closedByUser = true
      addMessage('interviewer', data.content)
      setPhaseBadge('done')
      setUIState('done')
      break

    case 'report':
      stopTtsAudio()
      removeTyping()
      closedByUser = true
      lastReportId.value = data.id || null
      reportCoach.value = null
      reportCoachError.value = ''
      showReport(data.report)
      setUIState('done')
      break

    case 'error':
      removeTyping()
      addMessage('interviewer', '⚠️ 出错了: ' + data.content)
      setUIState('active')
      break
  }
}

function sendCreate(resume: boolean): void {
  // Bind the retry loop to the socket that existed when this was called, so a
  // loop left over from a previous connection can never send on a new one.
  const target = ws
  if (!target || createSentForSocket === target) return // already sent on this socket
  const payload: Record<string, unknown> = { action: 'create', resume }
  if (currentJd) payload.jd = currentJd
  const trySend = () => {
    if (target !== ws) return // socket replaced — abandon this loop
    if (target.readyState === WebSocket.OPEN) {
      createSentForSocket = target
      createRetryTimer = null
      target.send(JSON.stringify(payload))
    } else {
      createRetryTimer = window.setTimeout(trySend, 150)
    }
  }
  trySend()
}

function clearCreateRetry(): void {
  if (createRetryTimer !== null) {
    clearTimeout(createRetryTimer)
    createRetryTimer = null
  }
}

function scheduleReconnect(): void {
  reconnectAttempts++
  if (reconnectAttempts > 5) {
    showInputHint('连接断开，重连失败，请返回首页重新开始', true)
    setUIState('done')
    return
  }
  showInputHint('连接断开，正在重连…（第 ' + reconnectAttempts + ' 次）', true)
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 10000)
  reconnectTimer = window.setTimeout(() => {
    shouldResume = true
    connectWs()
  }, delay)
}

function renderMessages(msgs: TranscriptMessage[]): void {
  streamId = null
  streaming.value = false
  pendingVoiceMsgId.value = null
  messages.value = []
  for (const m of msgs || []) {
    if (m.role === 'interviewer') {
      messages.value.push({ id: nextMsgId++, role: 'interviewer', content: m.content || '', phase: m.phase })
    } else if (m.audio_url) {
      messages.value.push({
        id: nextMsgId++,
        role: 'candidate',
        audio_url: m.audio_url,
        audio_duration: m.audio_duration || 0,
        transcript: m.content || '',
        pending: false,
      })
    } else {
      messages.value.push({ id: nextMsgId++, role: 'candidate', content: m.content || '' })
    }
  }
}

// ── Actions ───────────────────────────────────────────────
export function startInterview(): void {
  showView('interview')
  closedByUser = false
  sessionId = null
  shouldResume = false
  reconnectAttempts = 0
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  clearInputHint()
  setPhaseBadge(null)
  if (!connected.value || !ws || ws.readyState !== WebSocket.OPEN) connectWs()
  setUIState('active')
  messages.value = []
  streamId = null
  pendingVoiceMsgId.value = null
  clearCreateRetry()
  createSentForSocket = null
  sendCreate(false)
}

export function backHome(): void {
  resetInterviewState()
  showView('home')
}

export function sendAnswer(): void {
  if (uiState.value !== 'active' || streaming.value) return
  const text = inputText.value.trim()
  if (!text || !connected.value || !ws) return
  addMessage('candidate', text)
  inputText.value = ''
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'answer', content: text }))
  }
}

export function endInterview(): void {
  if (!connected.value || !ws) return
  if (recording.value) cancelRecording()
  stopTtsAudio()
  closedByUser = true
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'end' }))
  }
  setUIState('done')
}

// ── Voice recording (STT) ─────────────────────────────────
const MAX_RECORD_MS = 300000 // 5 minutes

let audioCtx: AudioContext | null = null
let mediaStream: MediaStream | null = null
let sourceNode: MediaStreamAudioSourceNode | null = null
let processorNode: ScriptProcessorNode | null = null
let pcmChunks: Int16Array[] = []
let recStartTs = 0
let recTimer: number | null = null
let recordingStarting = false

export function toggleRecording(): void {
  if (recording.value) stopRecording()
  else void startRecording()
}

function teardownRecorder(): void {
  if (recTimer !== null) {
    clearInterval(recTimer)
    recTimer = null
  }
  try {
    processorNode?.disconnect()
    sourceNode?.disconnect()
  } catch {
    /* ignore */
  }
  try {
    audioCtx?.close()
  } catch {
    /* ignore */
  }
  if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop())
  audioCtx = null
  sourceNode = null
  processorNode = null
  mediaStream = null
}

async function startRecording(): Promise<void> {
  if (recording.value || recordingStarting) return
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showInputHint('当前浏览器不支持录音（需要 HTTPS 或 localhost）', true)
    return
  }
  recordingStarting = true
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    recordingStarting = false
    showInputHint('无法访问麦克风，请检查浏览器权限', true)
    return
  }
  const Ctx: typeof AudioContext =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  try {
    audioCtx = new Ctx({ sampleRate: 16000 })
    sourceNode = audioCtx.createMediaStreamSource(mediaStream)
    processorNode = audioCtx.createScriptProcessor(4096, 1, 1)
  } catch {
    try {
      audioCtx?.close()
    } catch {
      /* ignore */
    }
    if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop())
    audioCtx = null
    mediaStream = null
    recordingStarting = false
    showInputHint('无法初始化录音，请重试', true)
    return
  }
  pcmChunks = []
  processorNode.onaudioprocess = (e: AudioProcessingEvent) => {
    pcmChunks.push(downsample(e.inputBuffer.getChannelData(0), audioCtx ? audioCtx.sampleRate : 44100, 16000))
  }
  sourceNode.connect(processorNode)
  processorNode.connect(audioCtx.destination)

  recordingStarting = false
  recording.value = true
  recStartTs = Date.now()
  recTimer = window.setInterval(() => {
    const elapsed = Date.now() - recStartTs
    showInputHint('正在录音 ' + fmtDur(elapsed / 1000) + '（最长 5 分钟，点 ⏹ 停止）')
    if (elapsed >= MAX_RECORD_MS) stopRecording()
  }, 200)
}

function stopRecording(): void {
  if (!recording.value) return
  teardownRecorder()
  recording.value = false
  clearInputHint()

  const totalLen = pcmChunks.reduce((s, c) => s + c.length, 0)
  const merged = new Int16Array(totalLen)
  let off = 0
  for (const c of pcmChunks) {
    merged.set(c, off)
    off += c.length
  }
  const durationSec = totalLen / 16000
  if (!totalLen) {
    showInputHint('没有录到声音，请重试', true)
    return
  }

  const wavBlob = pcmToWav(merged, 16000)
  const localUrl = URL.createObjectURL(wavBlob)
  const id = nextMsgId++
  pendingVoiceMsgId.value = id
  messages.value.push({
    id,
    role: 'candidate',
    audio_url: localUrl,
    audio_duration: durationSec,
    pending: true,
    status: '识别中…',
  })

  const reader = new FileReader()
  reader.onload = () => {
    const result = reader.result as string
    const b64 = result.split(',')[1]
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          action: 'answer_audio',
          audio_base64: b64,
          duration_ms: Math.round(durationSec * 1000),
        }),
      )
    } else {
      showInputHint('连接已断开，语音未发送', true)
      failVoiceMessage('发送失败')
    }
  }
  reader.onerror = () => {
    showInputHint('读取音频失败', true)
    failVoiceMessage('发送失败')
  }
  reader.readAsDataURL(wavBlob)
}

function failVoiceMessage(status: string): void {
  const id = pendingVoiceMsgId.value
  pendingVoiceMsgId.value = null
  if (id === null) return
  const msg = messages.value.find((m) => m.id === id)
  if (msg) {
    msg.pending = false
    msg.status = status
  }
}

export function cancelRecording(): void {
  if (!recording.value) return
  teardownRecorder()
  recording.value = false
  pcmChunks = []
  clearInputHint()
}

function handleCandidateVoice(data: CandidateVoiceData): void {
  const id = pendingVoiceMsgId.value
  pendingVoiceMsgId.value = null
  if (id === null) return
  const msg = messages.value.find((m) => m.id === id)
  if (!msg) return
  if (data.error) {
    msg.pending = false
    msg.status = data.error
    return
  }
  msg.transcript = data.text || ''
  msg.pending = false
  msg.status = ''
  if (data.audio_url) msg.audio_url = data.audio_url
}

// ── Report modal ──────────────────────────────────────────
export const report = ref<Report | null>(null)

export function showReport(r: Report): void {
  report.value = r
}

export function closeReport(): void {
  report.value = null
  // 面试已完成：对话界面已无可操作内容，关闭报告后直接回首页。
  if (uiState.value === 'done') {
    resetInterviewState()
    showView('home')
  }
}

// ── History ───────────────────────────────────────────────
export const historyDetail = ref<HistoryRecord | null>(null)
export const historyLoading = ref(false)
export const historyError = ref('')
export const progressGroups = ref<ProgressGroup[]>([])

export async function openHistory(): Promise<void> {
  showView('history')
  await loadHistory()
}

export async function loadHistory(): Promise<void> {
  historyLoading.value = true
  historyError.value = ''
  historyDetail.value = null
  try {
    progressGroups.value = await api.listProgress()
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    historyLoading.value = false
  }
}

export async function viewHistoryDetail(id: string): Promise<void> {
  historyLoading.value = true
  historyError.value = ''
  try {
    historyDetail.value = await api.getHistory(id)
  } catch (e) {
    historyDetail.value = null
    historyError.value = e instanceof Error ? e.message : '记录不存在'
  } finally {
    historyLoading.value = false
  }
}

export function backToList(): void {
  historyDetail.value = null
  historyError.value = ''
}

export async function deleteHistory(id: string): Promise<void> {
  if (!window.confirm('确定删除这条面试记录吗？')) return
  await api.deleteHistory(id)
  backToList()
  await loadHistory()
}

/** 重新面试同一岗位：复用历史记录的 JD（旧记录无 JD 时用岗位名回退）。 */
export async function reInterview(id: string): Promise<void> {
  const rec = await api.getHistory(id)
  currentJd =
    rec.jd ??
    ({
      profile: {
        role_title: rec.role_title,
        company_name: rec.company_name,
      },
    } as JdAnalysis)
  plan.value = currentJd
  startInterview()
}

// ── Coach（教练复盘） ──────────────────────────────────────
export const coachLoading = ref(false)

/** 为当前详情记录生成（或读取缓存的）教练复盘。 */
export async function generateCoach(id: string): Promise<void> {
  if (!historyDetail.value || historyDetail.value.id !== id) return
  coachLoading.value = true
  try {
    historyDetail.value.coach = await api.generateCoach(id)
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : '生成失败'
  } finally {
    coachLoading.value = false
  }
}

// ── Report-modal coach（面试结束即刻可见） ────────────────
export const lastReportId = ref<string | null>(null)
export const reportCoach = ref<CoachReport | null>(null)
export const reportCoachLoading = ref(false)
export const reportCoachError = ref('')

/** 为刚结束的这场面试生成教练复盘（服务端缓存，重复打开不重复调 LLM）。 */
export async function generateReportCoach(): Promise<void> {
  const id = lastReportId.value
  if (!id || reportCoachLoading.value) return
  reportCoachLoading.value = true
  reportCoachError.value = ''
  try {
    reportCoach.value = await api.generateCoach(id)
  } catch (e) {
    reportCoachError.value = e instanceof Error ? e.message : '生成失败'
  } finally {
    reportCoachLoading.value = false
  }
}

// ── Helpers ───────────────────────────────────────────────
function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function downsample(input: Float32Array, fromRate: number, toRate: number): Int16Array {
  const ratio = fromRate / toRate
  const len = Math.floor(input.length / ratio)
  const out = new Int16Array(len)
  for (let i = 0; i < len; i++) {
    const v = Math.max(-1, Math.min(1, input[Math.round(i * ratio)]))
    out[i] = Math.round(v * 32767)
  }
  return out
}

function writeStr(view: DataView, offset: number, str: string): void {
  for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
}

function pcmToWav(samples: Int16Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  writeStr(view, 0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeStr(view, 8, 'WAVE')
  writeStr(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeStr(view, 36, 'data')
  view.setUint32(40, samples.length * 2, true)
  let offset = 44
  for (let i = 0; i < samples.length; i++, offset += 2) {
    view.setInt16(offset, samples[i], true)
  }
  return new Blob([view], { type: 'audio/wav' })
}

// Register the 401 handler (must be set after logout is defined).
api.onUnauthorized(() => logout())

// Initial UI state.
setUIState('pre')
