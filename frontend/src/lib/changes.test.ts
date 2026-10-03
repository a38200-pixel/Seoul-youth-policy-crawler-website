import { describe, expect, it } from 'vitest'
import { CHANGE_FILTERS, badgeText, badgeTone, eventLabel, formatChange } from './changes'
import { ddayTone, deadlineLine, extractEndTime } from './deadline'

describe('eventLabel (이벤트 문구 선택 규칙)', () => {
  it('deactivated: expired → 마감됨', () => {
    expect(eventLabel('deactivated', 'expired')).toBe('마감됨')
    expect(eventLabel('deactivated', 'expired', true)).toBe('마감됨')
  })

  it('deactivated: early 는 마감일 유무를 알면 문구가 갈리고, 모르면 중립 문구', () => {
    expect(eventLabel('deactivated', 'early', true)).toBe('마감일 전에 목록에서 내려감')
    expect(eventLabel('deactivated', 'early', false)).toBe('게시 종료')
    expect(eventLabel('deactivated', 'early')).toBe('목록에서 내려감')
  })

  it('deactivated: reason 이 없으면 게시 종료', () => {
    expect(eventLabel('deactivated', null)).toBe('게시 종료')
  })

  it('status_changed 는 사이트 표기 변경', () => {
    expect(eventLabel('status_changed', null)).toBe('사이트 표기 변경')
  })

  it('나머지 유형', () => {
    expect(eventLabel('new', null)).toBe('신규')
    expect(eventLabel('extended', null)).toBe('마감 연장')
    expect(eventLabel('shortened', null)).toBe('마감 단축')
    expect(eventLabel('period_changed', null)).toBe('기간 변경')
    expect(eventLabel('reactivated', null)).toBe('다시 게시됨')
  })
})

describe('formatChange (old → new)', () => {
  it('상태·마감일 변경', () => {
    expect(formatChange('status_changed', '모집중', '모집예정')).toBe('모집중 → 모집예정')
    expect(formatChange('extended', '2026-10-08', '2026-10-10')).toBe('2026-10-08 → 2026-10-10')
  })

  it('기간 변경은 JSON 을 읽기 쉬운 문자열로', () => {
    const before = JSON.stringify({ period_type: 'open', start_date: '2026-09-20', end_date: null })
    const after = JSON.stringify({ period_type: 'dated', start_date: '2026-09-20', end_date: '2026-10-20' })
    expect(formatChange('period_changed', before, after)).toBe(
      'open 2026-09-20 ~ - → dated 2026-09-20 ~ 2026-10-20',
    )
  })

  it('값이 의미 없는 유형은 null', () => {
    expect(formatChange('new', null, null)).toBeNull()
    expect(formatChange('deactivated', '1', '0')).toBeNull()
    expect(formatChange('reactivated', '0', '1')).toBeNull()
    expect(formatChange('status_changed', null, null)).toBeNull()
  })
})

describe('필터 칩·배지', () => {
  it('마감 연장·단축 칩은 두 유형을 묶는다(API 는 type 을 하나만 받음)', () => {
    expect(CHANGE_FILTERS.find((f) => f.id === 'extend')?.types).toEqual(['extended', 'shortened'])
    expect(CHANGE_FILTERS[0].types).toEqual([])
  })

  it('배지 문구와 색 톤', () => {
    expect(badgeText({ type: 'new', label: 'NEW' })).toBe('NEW')
    expect(badgeText({ type: 'extended', label: '연장' })).toBe('마감 연장')
    expect(badgeText({ type: 'shortened', label: '단축' })).toBe('마감 단축')
    expect(badgeText({ type: 'status_changed', label: '상태 변경' })).toBe('사이트 표기 변경')
    expect(badgeText({ type: 'period_changed', label: '기간 변경' })).toBe('기간 변경')
    expect(badgeTone('new')).toBe('new')
    expect(badgeTone('extended')).toBe('up')
    expect(badgeTone('shortened')).toBe('down')
    expect(badgeTone('reactivated')).toBe('status')
  })
})

describe('D-Day 색 단계와 마감 줄', () => {
  it('오늘 마감 / D-1~D-3 / 그 밖', () => {
    expect(ddayTone({ group: 'recruiting', d_day: 0 })).toBe('today')
    expect(ddayTone({ group: 'recruiting', d_day: 1 })).toBe('soon')
    expect(ddayTone({ group: 'recruiting', d_day: 3 })).toBe('soon')
    expect(ddayTone({ group: 'recruiting', d_day: 4 })).toBe('normal')
    expect(ddayTone({ group: 'upcoming', d_day: 2 })).toBe('normal') // '시작 D-2' 는 마감 임박이 아니다
    expect(ddayTone({ group: 'always', d_day: null })).toBe('normal')
  })

  it('마감 MM.DD (요일), 시각이 있으면 함께', () => {
    expect(deadlineLine({ end_date: '2026-10-06', period_text: '2026-09-29 ~ 2026-10-06' })).toBe('마감 10.06 (화)')
    expect(deadlineLine({ end_date: '2026-10-06', period_text: '2026-09-29 ~ 2026-10-06 18 : 00' })).toBe(
      '마감 10.06 (화) 18:00',
    )
    expect(deadlineLine({ end_date: '2026-10-06', period_text: '2026-09-29 ~ 2026-10-06 00 : 00' })).toBe(
      '마감 10.06 (화)',
    ) // 00:00 은 날짜만 의미
    expect(deadlineLine({ end_date: null, period_text: '상시' })).toBeNull()
  })

  it('extractEndTime 은 시작일을 만들지 않고 마감 시각만 꺼낸다', () => {
    expect(extractEndTime('~ 2026-10-08 09 : 30')).toBe('09:30')
    expect(extractEndTime('상시 [ 선착순 마감 ]')).toBeNull()
    expect(extractEndTime(null)).toBeNull()
  })
})
