import { daysInMonth, parseMonth } from './dates'

export type CalendarCell = { date: string; day: number }

/**
 * 일요일 시작 달력 격자. 1일의 요일에 맞춰 앞을 null 로 채우고 마지막 주도 7칸으로 맞춘다.
 * 잘못된 month 면 빈 배열.
 */
export function buildMonthGrid(month: string): (CalendarCell | null)[][] {
  const p = parseMonth(month)
  if (!p) return []
  const lead = new Date(Date.UTC(p.y, p.m - 1, 1)).getUTCDay()
  const days = daysInMonth(p.y, p.m)
  const cells: (CalendarCell | null)[] = Array.from({ length: lead }, () => null)
  for (let day = 1; day <= days; day += 1) {
    const date = `${String(p.y).padStart(4, '0')}-${String(p.m).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    cells.push({ date, day })
  }
  while (cells.length % 7 !== 0) cells.push(null)
  const weeks: (CalendarCell | null)[][] = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}

// 점 강도 기준. 실데이터에서 날짜별 마감 건수가 1~28건이라 점 하나로는 구분이 안 되어 3단계로 나눈다.
export const INTENSITY_MID_FROM = 6 // 이 건수부터 '중간'
export const INTENSITY_HIGH_FROM = 16 // 이 건수부터 '진함'

export type Intensity = 0 | 1 | 2 | 3

/** 0건 → 0, 1~5건 → 1(연함), 6~15건 → 2(중간), 16건 이상 → 3(진함). */
export function intensityLevel(count: number): Intensity {
  if (!(count > 0)) return 0
  if (count >= INTENSITY_HIGH_FROM) return 3
  if (count >= INTENSITY_MID_FROM) return 2
  return 1
}

export const INTENSITY_LEGEND: { level: Intensity; label: string }[] = [
  { level: 1, label: `1~${INTENSITY_MID_FROM - 1}건` },
  { level: 2, label: `${INTENSITY_MID_FROM}~${INTENSITY_HIGH_FROM - 1}건` },
  { level: 3, label: `${INTENSITY_HIGH_FROM}건 이상` },
]
