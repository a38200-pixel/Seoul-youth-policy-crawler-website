import type { Program } from '../api/types'
import { formatMonthDay, weekdayLabel } from './dates'

export type DdayTone = 'today' | 'soon' | 'normal'

/**
 * D-Day 색 단계. 서버가 준 group·d_day 숫자만 쓴다(브라우저 시계 사용 안 함).
 * 오늘 마감(d_day 0) → today, D-1~D-3 → soon. 모집예정('시작 D-n')은 마감 임박이 아니므로 normal.
 */
export function ddayTone(p: Pick<Program, 'group' | 'd_day'>): DdayTone {
  if (p.group !== 'recruiting' || p.d_day === null) return 'normal'
  if (p.d_day === 0) return 'today'
  if (p.d_day >= 1 && p.d_day <= 3) return 'soon'
  return 'normal'
}

const END_TIME = /~\s*\d{4}-\d{2}-\d{2}\s+(\d{1,2})\s*:\s*(\d{2})/

/** 신청기간 원문에서 마감 시각을 꺼낸다. 시각이 없거나 00:00(날짜만 의미)이면 null. 시작일은 만들지 않는다. */
export function extractEndTime(periodText: string | null | undefined): string | null {
  if (!periodText) return null
  const match = END_TIME.exec(periodText)
  if (!match) return null
  const hh = match[1].padStart(2, '0')
  const mm = match[2]
  return hh === '00' && mm === '00' ? null : `${hh}:${mm}`
}

/** '마감 10.06 (화)' (+ ' 18:00'). end_date 가 없으면 null. */
export function deadlineLine(p: Pick<Program, 'end_date' | 'period_text'>): string | null {
  if (!p.end_date) return null
  const day = formatMonthDay(p.end_date)
  if (!day) return null
  const base = `마감 ${day} (${weekdayLabel(p.end_date)})`
  const time = extractEndTime(p.period_text)
  return time ? `${base} ${time}` : base
}
