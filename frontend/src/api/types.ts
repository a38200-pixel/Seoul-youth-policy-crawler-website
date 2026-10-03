// 백엔드(backend/api/main.py)의 응답 모양. 필드 이름은 서버가 정한 그대로다.

export type Badge = {
  type: string
  label: string
  detail: string | null
  detected_at: string | null
}

export type Program = {
  source_id: string
  title: string | null
  category: string | null
  organization: string | null
  display_status: string
  group: string
  d_day: number | null
  d_day_label: string | null
  source_status: string | null
  period_text: string | null
  start_date: string | null
  end_date: string | null
  apply_url: string | null
  source_url: string | null
  first_seen_at: string | null
  badges: Badge[]
}

export type TabCounts = { deadline: number; always: number; etc: number }

export type ProgramList = {
  items: Program[]
  total: number
  counts: TabCounts
}

export type ChangeType =
  | 'new'
  | 'extended'
  | 'shortened'
  | 'period_changed'
  | 'status_changed'
  | 'deactivated'
  | 'reactivated'

export type HistoryItem = {
  id: number | null
  change_type: ChangeType
  old_value: string | null
  new_value: string | null
  reason: string | null
  detected_at: string
}

export type ProgramDetail = Program & {
  summary: string | null
  target: string | null
  schedule_text: string | null
  is_active: boolean
  history: HistoryItem[]
}

export type ChangeItem = {
  id: number | null
  type: ChangeType
  source_id: string
  title: string | null
  detected_at: string
  old_value: string | null
  new_value: string | null
  reason: string | null
}

export type ChangeList = {
  days: number
  total: number
  counts: Partial<Record<ChangeType, number>>
  items: ChangeItem[]
}

export type Meta = {
  today: string
  active_count: number
  expired_active_count: number
  tab_counts: TabCounts & { all: number }
  last_collected_at: string | null
  window_days: number
  events_7d: Partial<Record<ChangeType, number>>
  new_7d: number
  baseline_date: string
}

export type CalendarDay = { date: string; count: number }

export type CalendarResponse = {
  month: string
  today: string
  days: CalendarDay[]
}

export type ProgramTab = 'deadline' | 'always' | 'etc' | 'all'
