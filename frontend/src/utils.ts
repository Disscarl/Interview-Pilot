// Small shared utilities.

export function fmtDur(sec: number): string {
  const s = Math.max(0, Math.round(sec || 0))
  const m = Math.floor(s / 60)
  const rem = s % 60
  return (m > 0 ? m + ':' : '0:') + String(rem).padStart(2, '0')
}

export const PHASE_LABELS: Record<string, string> = {
  intro: '自我介绍',
  warm_up: '暖场',
  tech_1: '专业基础',
  tech_2: '项目深挖',
  tech_3: '开放题',
  closing: '收尾',
  evaluate: '评估中',
}

export function phaseLabel(phase?: string): string {
  return (phase && PHASE_LABELS[phase]) || ''
}
