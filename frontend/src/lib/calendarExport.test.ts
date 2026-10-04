import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  GOOGLE_DETAILS_MAX,
  GOOGLE_RENDER_URL,
  compactYmd,
  googleCalendarUrl,
  nextDay,
  truncateText,
} from './calendarExport'

afterEach(() => {
  vi.useRealTimers()
})

const base = {
  title: '청년 공고',
  endDate: '2026-10-09',
  organization: '서울시',
  sourceUrl: 'https://youth.seoul.go.kr/infoData/sprtInfo/view.do?sprtInfoId=74445&key=2309130006',
}

const params = (url: string) => new URL(url).searchParams

describe('nextDay (마감일 +1일)', () => {
  it('평범한 날, 월말, 연말, 윤년', () => {
    expect(nextDay('2026-10-09')).toBe('2026-10-10')
    expect(nextDay('2026-10-31')).toBe('2026-11-01')
    expect(nextDay('2026-12-31')).toBe('2027-01-01') // 연말 경계
    expect(nextDay('2028-02-28')).toBe('2028-02-29')
    expect(nextDay('2028-02-29')).toBe('2028-03-01')
    expect(nextDay('2027-02-28')).toBe('2027-03-01')
  })

  it('날짜가 아니면 null', () => {
    expect(nextDay(null)).toBeNull()
    expect(nextDay('abc')).toBeNull()
    expect(nextDay('2026-02-30')).toBeNull()
  })

  it('현재 시각·시간대와 무관하다', () => {
    vi.useFakeTimers()
    for (const now of ['2000-01-01T00:00:00Z', '2026-12-31T23:59:59Z', '2099-06-15T12:00:00+14:00']) {
      vi.setSystemTime(new Date(now))
      expect(nextDay('2026-12-31')).toBe('2027-01-01')
      expect(params(googleCalendarUrl(base)!).get('dates')).toBe('20261009/20261010')
    }
  })
})

describe('compactYmd', () => {
  it('YYYY-MM-DD → YYYYMMDD', () => {
    expect(compactYmd('2026-01-05')).toBe('20260105')
    expect(compactYmd('2026-13-01')).toBeNull()
  })
})

describe('googleCalendarUrl', () => {
  it('구글 캘린더 템플릿 링크: 제목, 마감일/마감일+1일, 기관·상세 링크', () => {
    const url = googleCalendarUrl(base)!
    expect(url.startsWith(`${GOOGLE_RENDER_URL}?`)).toBe(true)
    const p = params(url)
    expect(p.get('action')).toBe('TEMPLATE')
    expect(p.get('text')).toBe('[마감] 청년 공고')
    expect(p.get('dates')).toBe('20261009/20261010')
    expect(p.get('details')).toBe(`기관: 서울시\n상세: ${base.sourceUrl}`)
  })

  it('연말 마감은 다음 해 1월 1일로 끝난다', () => {
    expect(params(googleCalendarUrl({ ...base, endDate: '2026-12-31' })!).get('dates')).toBe('20261231/20270101')
    expect(params(googleCalendarUrl({ ...base, endDate: '2026-10-31' })!).get('dates')).toBe('20261031/20261101')
  })

  it('URLSearchParams 로 인코딩한다(&, #, 줄바꿈, 한글이 값 안에 안전하게 들어간다)', () => {
    const url = googleCalendarUrl({ ...base, title: 'A&B #1 100% 한글', organization: '기관 & 센터' })!
    expect(url).not.toContain(' ') // 공백이 그대로 남지 않는다
    expect(url).not.toContain('\n')
    expect(url.split('?')[1].split('&').length).toBe(4) // 제목 안의 & 가 파라미터를 가르지 않는다
    expect(params(url).get('text')).toBe('[마감] A&B #1 100% 한글')
    expect(params(url).get('details')).toContain('기관: 기관 & 센터')
    expect(url).toContain('%26') // & 는 %26 로 인코딩
    expect(url).toContain('%23') // # 는 %23 으로 인코딩
  })

  it('details 는 300자를 넘지 않게 자른다', () => {
    const url = googleCalendarUrl({ ...base, organization: '기관'.repeat(200), sourceUrl: `https://x.test/${'a'.repeat(500)}` })!
    const details = params(url).get('details')!
    expect(Array.from(details).length).toBeLessThanOrEqual(GOOGLE_DETAILS_MAX)
    expect(details.endsWith('…')).toBe(true)
    expect(url.length).toBeLessThan(2000) // 링크 전체도 짧게 유지된다
  })

  it('기관과 링크가 없으면 details 를 빼고, 제목이 없으면 자리표시를 쓴다', () => {
    const url = googleCalendarUrl({ title: null, endDate: '2026-10-09', organization: null, sourceUrl: null })!
    expect(params(url).has('details')).toBe(false)
    expect(params(url).get('text')).toBe('[마감] (제목 없음)')
  })

  it('마감일이 날짜가 아니면 null', () => {
    expect(googleCalendarUrl({ ...base, endDate: null })).toBeNull()
    expect(googleCalendarUrl({ ...base, endDate: '2026-02-30' })).toBeNull()
  })
})

describe('truncateText', () => {
  it('글자(코드 포인트) 단위로 자르고 이모지를 쪼개지 않는다', () => {
    expect(truncateText('가나다라마', 5)).toBe('가나다라마')
    expect(truncateText('가나다라마바', 5)).toBe('가나다라…')
    expect(truncateText('😀😀😀', 3)).toBe('😀😀😀')
    expect(truncateText('😀😀😀😀', 3)).toBe('😀😀…')
  })
})

