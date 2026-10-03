// 날짜 문자열(YYYY-MM-DD) 다루기. 브라우저 시계와 시간대를 쓰지 않는다:
// 요일은 문자열의 연·월·일을 UTC 자정으로 해석해서 계산하므로 사용자 PC 의 시간대에 따라 하루가 어긋나지 않는다.

export const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const

const YMD = /^(\d{4})-(\d{2})-(\d{2})/
const YM = /^(\d{4})-(\d{2})$/
const TIME = /^\d{4}-\d{2}-\d{2}[T ](\d{2}:\d{2})/

export type Ymd = { y: number; m: number; d: number }

/** 'YYYY-MM-DD…' → 연·월·일. 형식이 아니거나 존재하지 않는 날짜(2026-02-30)면 null. */
export function parseYmd(value: string | null | undefined): Ymd | null {
  if (!value) return null
  const match = YMD.exec(value)
  if (!match) return null
  const y = Number(match[1])
  const m = Number(match[2])
  const d = Number(match[3])
  const dt = new Date(Date.UTC(y, m - 1, d))
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null
  return { y, m, d }
}

/** 0(일)~6(토). 날짜가 아니면 null. */
export function weekdayIndex(value: string | null | undefined): number | null {
  const p = parseYmd(value)
  return p ? new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay() : null
}

export function weekdayLabel(value: string | null | undefined): string {
  const i = weekdayIndex(value)
  return i === null ? '' : WEEKDAYS[i]
}

const pad2 = (n: number) => String(n).padStart(2, '0')

/** '2026-10-06' → '10.06' */
export function formatMonthDay(value: string | null | undefined): string {
  const p = parseYmd(value)
  return p ? `${pad2(p.m)}.${pad2(p.d)}` : ''
}

/** '2026-10-06' → '10월 6일 (화)' (withWeekday=false 면 '10월 6일') */
export function formatKoreanDay(value: string | null | undefined, withWeekday = true): string {
  const p = parseYmd(value)
  if (!p) return ''
  const base = `${p.m}월 ${p.d}일`
  return withWeekday ? `${base} (${weekdayLabel(value)})` : base
}

/** '2026-10-03' → '2026.10.03 (토)' */
export function formatFullDate(value: string | null | undefined): string {
  const p = parseYmd(value)
  return p ? `${p.y}.${pad2(p.m)}.${pad2(p.d)} (${weekdayLabel(value)})` : ''
}

/** '2026-10-03T07:12:00+09:00' → '2026-10-03 07:12' (서버가 준 시각을 그대로 자른다. 시간대 변환 없음) */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return ''
  const t = TIME.exec(value)
  const date = YMD.exec(value)
  return date && t ? `${date[1]}-${date[2]}-${date[3]} ${t[1]}` : (date ? date[0] : '')
}

/** '2026-10-03T07:12:00+09:00' → '10.03 07:12' */
export function formatShortDateTime(value: string | null | undefined): string {
  const day = formatMonthDay(value)
  const t = value ? TIME.exec(value) : null
  return t ? `${day} ${t[1]}` : day
}

export function parseMonth(month: string | null | undefined): { y: number; m: number } | null {
  if (!month) return null
  const match = YM.exec(month)
  if (!match) return null
  const y = Number(match[1])
  const m = Number(match[2])
  return m >= 1 && m <= 12 ? { y, m } : null
}

/** '2026-10-06' → '2026-10' */
export function monthOf(value: string | null | undefined): string | null {
  const p = parseYmd(value)
  return p ? `${p.y}-${pad2(p.m)}` : null
}

/** 'YYYY-MM' 에서 delta 개월 이동. 잘못된 입력은 그대로 돌려준다. */
export function shiftMonth(month: string, delta: number): string {
  const p = parseMonth(month)
  if (!p) return month
  const index = p.y * 12 + (p.m - 1) + delta
  return `${String(Math.floor(index / 12)).padStart(4, '0')}-${pad2((index % 12) + 1)}`
}

export function daysInMonth(y: number, m: number): number {
  return new Date(Date.UTC(y, m, 0)).getUTCDate()
}

export function formatMonthTitle(month: string): string {
  const p = parseMonth(month)
  return p ? `${p.y}년 ${p.m}월` : month
}
