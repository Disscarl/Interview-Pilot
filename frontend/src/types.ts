// Shared frontend types (mirrors backend payload shapes).

export type ViewName = 'auth' | 'home' | 'interview' | 'history'

export type Role = 'interviewer' | 'candidate'

export interface TtsVoice {
  id: string
  label: string
}

export interface CompanyResearch {
  business?: string
  products?: string[]
  history_projects?: string[]
  market_position?: string
}

export interface Profile {
  company_name?: string
  company_type?: string
  industry?: string
  role_title?: string
  tech_stack?: string[]
  company_research?: CompanyResearch
}

export interface Stage {
  name?: string
  goal?: string
  focus?: string[]
}

export interface Plan {
  summary?: string
  focus_areas?: string[]
  stages?: Stage[]
}

export interface CandidateProfile {
  skills?: string[]
  projects?: string[]
  work_history?: string[]
  years_of_experience?: string
}

export interface JdAnalysis {
  profile?: Profile
  plan?: Plan
  candidate?: CandidateProfile
}

export interface ChatMessage {
  id: number
  role: Role
  content?: string
  phase?: string
  audio_url?: string
  audio_duration?: number
  typing?: boolean
  pending?: boolean
  transcript?: string
  status?: string
}

// Server-side transcript message (no client-only id/typing/pending fields).
export interface TranscriptMessage {
  role: Role
  content?: string
  phase?: string
  audio_url?: string
  audio_duration?: number
}

export interface ReportDimension {
  score: number
  comment?: string
}

export interface WeakPoint {
  area?: string
  description?: string
  suggestion?: string
}

export interface Report {
  overall_score?: number
  summary?: string
  dimension_scores?: Record<string, ReportDimension>
  highlights?: string[]
  weak_points?: WeakPoint[]
  recommended_topics?: string[]
}

export interface HistoryItem {
  id: string
  role_title?: string
  company_name?: string
  overall_score?: number
  created_at?: string
}

export interface HistoryRecord {
  id: string
  role_title?: string
  company_name?: string
  created_at?: string
  overall_score?: number
  report?: Report
  messages?: TranscriptMessage[]
}

export interface CandidateVoiceData {
  text?: string
  error?: string
  audio_url?: string
}

export type WsIncoming =
  | { type: 'created' }
  | { type: 'resume'; messages: TranscriptMessage[]; phase: string }
  | { type: 'message'; role: Role; content: string; phase?: string }
  | { type: 'thinking' }
  | { type: 'stream_token'; content: string }
  | { type: 'stream_end'; phase?: string }
  | { type: 'candidate_voice'; text?: string; error?: string; audio_url?: string }
  | { type: 'interview_end'; content: string }
  | { type: 'report'; report: Report }
  | { type: 'error'; content: string }
