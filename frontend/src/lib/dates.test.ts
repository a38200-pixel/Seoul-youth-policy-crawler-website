import { afterEach, describe, expect, it } from 'vitest'
import {
  daysInMonth,
  formatDateTime,
  formatFullDate,
  formatKoreanDay,
  formatMonthDay,
  formatShortDateTime,
  monthOf,
  parseYmd,
  shiftMonth,
  weekdayLabel,
} from './dates'

const originalTz = process.env.TZ
afterEach(() => {
  if (originalTz === undefined) delete process.env.TZ
  else process.env.TZ = originalTz
})

describe('요일 표시', () => {
  it('날짜 문자열에서 요일을 계산한다', () => {
    expect(weekdayLabel('2026-10-03')).toBe('토')
    expect(weekdayLabel('2026-10-04')).toBe('일')
    expect(weekdayLabel('2026-10-06')).toBe('화')
    expect(weekdayLabel('2024-02-29')).toBe('목')
  })

  it('브라우저 시간대가 바뀌어도 하루가 어긋나지 않는다(UTC+14 / UTC-11)', () => {
    for (const tz of ['Pacific/Kiritimati', 'Pacific/Pago_Pago', 'Asia/Seoul', 'America/Los_Angeles']) {
      process.env.TZ = tz
      expect(weekdayLabel('2026-10-06')).toBe('화')
      expect(formatKoreanDay('2026-10-06')).toBe('10월 6일 (화)')
      expect(formatMonthDay('2026-10-06')).toBe('10.06')
    }
  })

  it('존재하지 않는 날짜·형식 오류는 빈 문자열', () => {
    expect(weekdayLabel('2026-02-30')).toBe('')
    expect(weekdayLabel('abc')).toBe('')
    expect(weekdayLabel(null)).toBe('')
  })
})

describe('날짜 포맷', () => {
  it('월·일·요일 표기', () => {
    expect(formatMonthDay('2026-10-06')).toBe('10.06')
    expect(formatKoreanDay('2026-10-06')).toBe('10월 6일 (화)')
    expect(formatKoreanDay('2026-10-06', false)).toBe('10월 6일')
    expect(formatFullDate('2026-10-03')).toBe('2026.10.03 (토)')
  })

  it('서버 시각 문자열은 시간대 변환 없이 그대로 자른다', () => {
    expect(formatDateTime('2026-10-03T07:12:34.567+09:00')).toBe('2026-10-03 07:12')
    expect(formatDateTime('2026-10-03T23:59:00+09:00')).toBe('2026-10-03 23:59')
    expect(formatShortDateTime('2026-10-03T07:12:00+09:00')).toBe('10.03 07:12')
    expect(formatDateTime(null)).toBe('')
  })
})

describe('날짜 계산', () => {
  it('parseYmd 는 윤년을 구분한다', () => {
    expect(parseYmd('2024-02-29')).toEqual({ y: 2024, m: 2, d: 29 })
    expect(parseYmd('2025-02-29')).toBeNull()
    expect(parseYmd('2026-13-01')).toBeNull()
  })

  it('shiftMonth 는 연도를 넘긴다', () => {
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-10', 0)).toBe('2026-10')
    expect(shiftMonth('2026-10', 14)).toBe('2027-12')
  })

  it('monthOf, daysInMonth', () => {
    expect(monthOf('2026-10-06')).toBe('2026-10')
    expect(monthOf('x')).toBeNull()
    expect(daysInMonth(2024, 2)).toBe(29)
    expect(daysInMonth(2026, 10)).toBe(31)
  })
})
