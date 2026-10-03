import type { Badge, ChangeType } from '../api/types'

/**
 * 변경 이벤트 문구. status_changed 는 '사이트 표기 변경'.
 * deactivated 는 reason 으로 나눈다: expired → '마감됨'.
 * early 는 '마감일이 있던 공고'인지에 따라 문구가 갈리는데, /api/changes 응답에는 end_date·period_type 이 없어 판별할 수 없다.
 * hasEndDate 를 모르면(undefined) 어느 쪽에도 맞는 '목록에서 내려감'을 쓴다.
 */
export function eventLabel(type: ChangeType, reason: string | null | undefined, hasEndDate?: boolean): string {
  switch (type) {
    case 'new':
      return '신규'
    case 'extended':
      return '마감 연장'
    case 'shortened':
      return '마감 단축'
    case 'period_changed':
      return '기간 변경'
    case 'status_changed':
      return '사이트 표기 변경'
    case 'reactivated':
      return '다시 게시됨'
    case 'deactivated':
      if (reason === 'expired') return '마감됨'
      if (reason === 'early') {
        if (hasEndDate === true) return '마감일 전에 목록에서 내려감'
        if (hasEndDate === false) return '게시 종료'
        return '목록에서 내려감'
      }
      return '게시 종료'
  }
}

function periodValue(value: string): string {
  try {
    const d = JSON.parse(value) as { period_type?: string; start_date?: string | null; end_date?: string | null }
    return `${d.period_type ?? '?'} ${d.start_date || '-'} ~ ${d.end_date || '-'}`
  } catch {
    return value
  }
}

/** 'old → new' 표시용 문자열. 값이 의미 없는 유형(신규·내려감·다시 게시됨)이나 값이 없으면 null. */
export function formatChange(type: ChangeType, oldValue: string | null, newValue: string | null): string | null {
  if (type === 'new' || type === 'deactivated' || type === 'reactivated') return null
  if (oldValue === null && newValue === null) return null
  if (type === 'period_changed') {
    return `${oldValue === null ? '-' : periodValue(oldValue)} → ${newValue === null ? '-' : periodValue(newValue)}`
  }
  return `${oldValue ?? '-'} → ${newValue ?? '-'}`
}

export type ChangeFilter = { id: string; label: string; types: ChangeType[] }

/** 유형 필터 칩. types 가 여러 개면 type 파라미터를 하나씩 요청해 합친다(API 가 type 을 하나만 받는다). 비어 있으면 전체. */
export const CHANGE_FILTERS: ChangeFilter[] = [
  { id: 'all', label: '전체', types: [] },
  { id: 'new', label: '신규', types: ['new'] },
  { id: 'extend', label: '마감 연장·단축', types: ['extended', 'shortened'] },
  { id: 'period', label: '기간 변경', types: ['period_changed'] },
  { id: 'status', label: '사이트 표기 변경', types: ['status_changed'] },
  { id: 'off', label: '목록에서 내려감', types: ['deactivated'] },
  { id: 'again', label: '다시 게시됨', types: ['reactivated'] },
]

export type BadgeTone = 'new' | 'up' | 'down' | 'status'

export function badgeTone(type: string): BadgeTone {
  if (type === 'new') return 'new'
  if (type === 'extended') return 'up'
  if (type === 'shortened') return 'down'
  return 'status'
}

/** 배지 문구. 배지의 존재·종류·detail 은 서버(badges 필드) 그대로이고, 시안의 표기명만 맞춰 보여 준다. */
export function badgeText(b: Pick<Badge, 'type' | 'label'>): string {
  switch (b.type) {
    case 'new':
      return 'NEW'
    case 'extended':
      return '마감 연장'
    case 'shortened':
      return '마감 단축'
    case 'status_changed':
      return '사이트 표기 변경'
    default:
      return b.label
  }
}
