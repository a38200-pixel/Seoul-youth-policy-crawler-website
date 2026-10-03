import { describe, expect, it } from 'vitest'
import { INTENSITY_HIGH_FROM, INTENSITY_MID_FROM, buildMonthGrid, intensityLevel } from './calendar'

const flat = (month: string) => buildMonthGrid(month).flat()

describe('buildMonthGrid', () => {
  it('2026-10 은 목요일에 시작한다(앞 4칸이 비고 1일이 5번째 칸)', () => {
    const weeks = buildMonthGrid('2026-10')
    expect(weeks[0].slice(0, 4)).toEqual([null, null, null, null])
    expect(weeks[0][4]).toEqual({ date: '2026-10-01', day: 1 })
    expect(weeks).toHaveLength(5)
    expect(weeks[4][6]).toEqual({ date: '2026-10-31', day: 31 }) // 10월 31일은 토요일
  })

  it('모든 주가 7칸이고 날짜 칸 수는 그 달의 일수와 같다', () => {
    for (const month of ['2026-10', '2026-02', '2024-02', '2023-02', '2026-12']) {
      const weeks = buildMonthGrid(month)
      expect(weeks.every((w) => w.length === 7)).toBe(true)
      const days = flat(month).filter((c) => c !== null)
      expect(days.map((c) => c!.day)).toEqual(days.map((_, i) => i + 1))
    }
  })

  it('윤년 2월은 29일, 평년 2월은 28일이다', () => {
    expect(flat('2024-02').filter(Boolean)).toHaveLength(29)
    expect(flat('2023-02').filter(Boolean)).toHaveLength(28)
    expect(flat('2024-02').filter(Boolean).at(-1)).toEqual({ date: '2024-02-29', day: 29 })
    expect(flat('2100-02').filter(Boolean)).toHaveLength(28) // 2100 은 윤년이 아니다
  })

  it('2026-02 는 일요일에 시작해 정확히 4주이고 빈 칸이 없다', () => {
    const weeks = buildMonthGrid('2026-02')
    expect(weeks).toHaveLength(4)
    expect(flat('2026-02').every((c) => c !== null)).toBe(true)
    expect(weeks[0][0]).toEqual({ date: '2026-02-01', day: 1 })
  })

  it('잘못된 month 는 빈 배열', () => {
    expect(buildMonthGrid('2026-13')).toEqual([])
    expect(buildMonthGrid('abc')).toEqual([])
  })
})

describe('intensityLevel (점 3단계)', () => {
  it('경계값: 5/6, 15/16', () => {
    expect(intensityLevel(5)).toBe(1)
    expect(intensityLevel(6)).toBe(2)
    expect(intensityLevel(15)).toBe(2)
    expect(intensityLevel(16)).toBe(3)
  })

  it('1건은 연함, 실데이터 최대 범위(28건)는 진함, 0 이하·NaN 은 0', () => {
    expect(intensityLevel(1)).toBe(1)
    expect(intensityLevel(28)).toBe(3)
    expect(intensityLevel(0)).toBe(0)
    expect(intensityLevel(-3)).toBe(0)
    expect(intensityLevel(Number.NaN)).toBe(0)
  })

  it('기준 상수와 일치한다', () => {
    expect(INTENSITY_MID_FROM).toBe(6)
    expect(INTENSITY_HIGH_FROM).toBe(16)
  })
})
