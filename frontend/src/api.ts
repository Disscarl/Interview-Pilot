// HTTP client with JWT bearer auth + typed endpoint helpers.
import { ref } from 'vue'
import type { CoachReport, HistoryRecord, JdAnalysis, ProgressGroup } from './types'

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

/** Default per-request timeout (ms). Long LLM pipelines pass a larger value. */
const DEFAULT_TIMEOUT_MS = 120_000
/** /api/jd/analyze runs up to 4 serial LLM calls — allow 5 minutes. */
const JD_ANALYZE_TIMEOUT_MS = 300_000

export async function apiFetch(
  url: string,
  opts: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const headers = new Headers(opts.headers || {})
  headers.set('Authorization', 'Bearer ' + authToken.value)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  // L18: combine the caller's signal (if any) with our timeout signal so the
  // timeout is not silently disabled when opts.signal is provided.
  const signal =
    opts.signal && typeof AbortSignal.any === 'function'
      ? AbortSignal.any([opts.signal, controller.signal])
      : opts.signal ?? controller.signal
  try {
    const resp = await fetch(url, { ...opts, headers, signal })
    if (resp.status === 401) {
      unauthorizedHandler()
      throw new Error('登录已过期，请重新登录')
    }
    return resp
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error('请求超时，请检查网络后重试')
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
}

interface ErrorDetail {
  msg?: string
  loc?: unknown
}

interface ErrorBody {
  detail?: string | ErrorDetail[]
}

function errMessage(resp: Response, data: ErrorBody, fallback: string): string {
  const detail = data.detail
  if (typeof detail === 'string' && detail) return detail
  // FastAPI 422 validation errors return detail as an array of {loc, msg, type}.
  if (Array.isArray(detail) && detail.length && typeof detail[0]?.msg === 'string') {
    return detail[0].msg as string
  }
  return fallback
}

export async function login(username: string, password: string): Promise<string> {
  const resp = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  // L19: parse after checking ok, so a non-JSON error body can't throw.
  const data = (await resp.json().catch(() => ({}))) as { token?: string } & ErrorBody
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
  const data = (await resp.json().catch(() => ({}))) as { token?: string } & ErrorBody
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
  const resp = await apiFetch(
    '/api/jd/analyze',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    JD_ANALYZE_TIMEOUT_MS,
  )
  const data = (await resp.json()) as JdAnalysis & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '解析失败，请重试'))
  return data
}

export async function extractResume(
  filename: string,
  dataBase64: string,
): Promise<{ text: string; truncated: boolean }> {
  let resp: Response
  try {
    resp = await apiFetch('/api/resume/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, data_base64: dataBase64 }),
    })
  } catch (e) {
    // L21: an expired-session 401 is already surfaced by apiFetch — don't
    // wrap it into a confusing "上传失败：登录已过期".
    const msg = e instanceof Error ? e.message : '网络错误'
    throw new Error(msg === '登录已过期，请重新登录' ? msg : '上传失败：' + msg)
  }
  const data = (await resp.json().catch(() => ({}))) as {
    text?: string
    truncated?: boolean
  } & ErrorBody
  if (!resp.ok) throw new Error('解析失败：' + errMessage(resp, data, filename))
  return { text: data.text || '', truncated: !!data.truncated }
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

export async function generateCoach(id: string): Promise<CoachReport> {
  const resp = await apiFetch('/api/history/' + encodeURIComponent(id) + '/coach', {
    method: 'POST',
  })
  const data = (await resp.json()) as { coach?: CoachReport } & ErrorBody
  if (!resp.ok) throw new Error(errMessage(resp, data, '生成失败'))
  return data.coach || {}
}
