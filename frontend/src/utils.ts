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

/** Ordered interview stages shown in the phase progress track (L22: includes
 * the evaluate terminal stage so the tracker shows 评估中 during evaluation). */
export const PHASE_ORDER = [
  'intro',
  'warm_up',
  'tech_1',
  'tech_2',
  'tech_3',
  'closing',
  'evaluate',
] as const

export function phaseLabel(phase?: string): string {
  return (phase && PHASE_LABELS[phase]) || ''
}
