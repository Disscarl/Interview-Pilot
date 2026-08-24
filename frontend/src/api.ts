// HTTP client with JWT bearer auth + typed endpoint helpers.
import { ref } from 'vue'
import type { HistoryItem, HistoryRecord, JdAnalysis, ProgressGroup } from './types'

export const authToken = ref<string>(localStorage.getItem('auth_token') || '')

export function getToken(): string {
  return authToken.value
}

export function setToken(token: string): void {
  authToken.value = token
  if (token) localStorage.setItem('auth_token', token)
  else localStorage.removeItem('auth_token')
}

type UnauthorizedHandler = () => void
let unauthorizedHandler: UnauthorizedHandler = () => {}

export function onUnauthorized(fn: UnauthorizedHandler): void {
  unauthorizedHandler = fn
}

export async function apiFetch(url: string, opts: RequestInit = {}): Promise<Response> {
  const headers = new Headers(opts.headers || {})
  headers.set('Authorization', 'Bearer ' + authToken.value)
  const resp = await fetch(url, { ...opts, headers })
  if (resp.status === 401) {
    unauthorizedHandler()
    throw new Error('登录已过期，请重新登录')
  }
  return resp
}

interface ErrorBody {
  detail?: string
}

function errMessage(resp: Response, data: ErrorBody, fallback: string): string {
  return data.detail || fallback
}

export async function login(username: string, password: string): Promise<string> {
  const resp = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = (await resp.json()) as { token?: string } & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '登录失败'))
  if (!data.token) throw new Error('登录失败')
  return data.token
}

export async function register(username: string, password: string): Promise<string> {
  const resp = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = (await resp.json()) as { token?: string } & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '注册失败'))
  if (!data.token) throw new Error('注册失败')
  return data.token
}

export interface AnalyzeJdPayload {
  text: string
  company?: string
  resume_text?: string
}

export async function analyzeJd(payload: AnalyzeJdPayload): Promise<JdAnalysis> {
  const resp = await apiFetch('/api/jd/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = (await resp.json()) as JdAnalysis & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '解析失败，请重试'))
  return data
}

export async function extractResume(filename: string, dataBase64: string): Promise<string> {
  let resp: Response
  try {
    resp = await apiFetch('/api/resume/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, data_base64: dataBase64 }),
    })
  } catch (e) {
    throw new Error('上传失败：' + (e instanceof Error ? e.message : '网络错误'))
  }
  const data = (await resp.json()) as { text?: string } & ErrorBody
  if (!resp.ok) throw new Error('解析失败：' + errMessage(resp, data, filename))
  return data.text || ''
}

export async function ttsPreview(text: string, voice: string, speed: number): Promise<string> {
  const resp = await apiFetch('/api/tts/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice, speed }),
  })
  const data = (await resp.json()) as { audio_base64?: string } & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '语音合成失败'))
  return data.audio_base64 || ''
}

export async function listHistory(): Promise<HistoryItem[]> {
  const resp = await apiFetch('/api/history')
  const data = (await resp.json()) as { interviews?: HistoryItem[] } & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '加载失败'))
  return data.interviews || []
}

export async function listProgress(): Promise<ProgressGroup[]> {
  const resp = await apiFetch('/api/history/progress')
  const data = (await resp.json()) as { groups?: ProgressGroup[] } & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '加载失败'))
  return data.groups || []
}

export async function getHistory(id: string): Promise<HistoryRecord> {
  const resp = await apiFetch('/api/history/' + encodeURIComponent(id))
  const data = (await resp.json()) as HistoryRecord & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '记录不存在'))
  return data
}

export async function deleteHistory(id: string): Promise<void> {
  const resp = await apiFetch('/api/history/' + encodeURIComponent(id), { method: 'DELETE' })
  if (!resp.ok) {
    const data = (await resp.json().catch(() => ({}))) as ErrorBody
    throw new Error(errMessage(resp, data, '删除失败'))
  }
}
