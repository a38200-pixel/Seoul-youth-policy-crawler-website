import { parseYmd } from './dates'

// 구글 캘린더에 추가하는 링크를 만드는 순수 함수. 현재 시각을 읽지 않는다:
// 마감일 +1일은 문자열의 연·월·일을 UTC 날짜로 계산할 뿐이라 사용자 PC 의 시계·시간대와 무관하다.

export const GOOGLE_RENDER_URL = 'https://calendar.google.com/calendar/render'
export const GOOGLE_TITLE_MAX = 200
export const GOOGLE_DETAILS_MAX = 300 // URL 길이 제한을 넘기지 않도록 details 는 짧게
export const IMPORT_NOTE = '추가한 시점의 마감일 기준이며 이후 변경은 자동 반영되지 않습니다'

const pad2 = (n: number) => String(n).padStart(2, '0')

/** 'YYYY-MM-DD' 의 다음 날('YYYY-MM-DD'). 날짜가 아니면 null. 12-31 → 다음 해 01-01, 윤년 2-28/2-29 도 맞는다. */
export function nextDay(ymd: string | null | undefined): string | null {
  const p = parseYmd(ymd)
  if (!p) return null
  const d = new Date(Date.UTC(p.y, p.m - 1, p.d + 1))
  return `${String(d.getUTCFullYear()).padStart(4, '0')}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`
}

/** 'YYYY-MM-DD' → 'YYYYMMDD'. 날짜가 아니면 null. */
export function compactYmd(ymd: string | null | undefined): string | null {
  const p = parseYmd(ymd)
  return p ? `${String(p.y).padStart(4, '0')}${pad2(p.m)}${pad2(p.d)}` : null
}

/** 문자(코드 포인트) 단위로 max 글자까지만 남긴다. 넘으면 마지막 글자를 '…' 로 바꾼다. */
export function truncateText(text: string, max: number): string {
  const chars = Array.from(text)
  return chars.length <= max ? text : chars.slice(0, max - 1).join('') + '…'
}

export type GoogleCalendarInput = {
  title: string | null
  endDate: string | null
  organization: string | null
  sourceUrl: string | null
}

/**
 * 구글 캘린더 '일정 추가' 링크. 종일 일정이라 dates 는 마감일/마감일+1일(YYYYMMDD/YYYYMMDD)이다.
 * 마감일이 날짜가 아니면 null. details 는 기관과 상세 링크만 담고 300자로 자른다. 인코딩은 URLSearchParams 가 한다.
 */
export function googleCalendarUrl({ title, endDate, organization, sourceUrl }: GoogleCalendarInput): string | null {
  const start = compactYmd(endDate)
  const end = compactYmd(nextDay(endDate))
  if (!start || !end) return null
  const lines: string[] = []
  if (organization) lines.push(`기관: ${truncateText(organization, 100)}`)
  if (sourceUrl) lines.push(`상세: ${sourceUrl}`)
  const params = new URLSearchParams()
  params.set('action', 'TEMPLATE')
  params.set('text', truncateText(`[마감] ${title || '(제목 없음)'}`, GOOGLE_TITLE_MAX))
  params.set('dates', `${start}/${end}`)
  if (lines.length > 0) params.set('details', truncateText(lines.join('\n'), GOOGLE_DETAILS_MAX))
  return `${GOOGLE_RENDER_URL}?${params.toString()}`
}
