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

/** 표시 규칙의 group(만료는 목록에 없다). */
export type GroupName = 'recruiting' | 'upcoming' | 'open' | 'always' | 'always_etc' | 'unknown'
export type GroupCounts = Record<GroupName, number>

export type ProgramList = {
  items: Program[]
  total: number
  counts: TabCounts
  /** counts 와 같은 집합(q·category 적용 후)의 group 별 건수. tab·date·group 과는 무관하다. */
  group_counts: GroupCounts
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
  /** 공고(programs 행)의 마감일. 행이 없거나 마감일이 없으면 null. */
  end_date: string | null
  period_type: string | null
}

export type ChangeList = {
  days: number
  total: number
  counts: Partial<Record<ChangeType, number>>
  items: ChangeItem[]
}

export type CategoryCount = { name: string; count: number }

export type Meta = {
  today: string
  active_count: number
  expired_active_count: number
  tab_counts: TabCounts & { all: number }
  /** 분야 칩: tab=all 과 같은 범위, count 내림차순(같으면 name 오름차순). name 으로 category 필터를 걸면 count 와 total 이 같다. */
  categories: CategoryCount[]
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
