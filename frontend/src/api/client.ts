import type {
  CalendarResponse,
  ChangeList,
  ChangeType,
  Meta,
  ProgramDetail,
  ProgramList,
  ProgramTab,
} from './types'

export type ApiErrorKind = 'db' | 'network' | 'http'

export class ApiError extends Error {
  kind: ApiErrorKind
  status: number | undefined

  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

type Params = Record<string, string | number | null | undefined>

/** 값이 없거나 빈 문자열인 파라미터는 빼고 쿼리스트링을 만든다. */
export function buildUrl(path: string, params: Params = {}): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${path}?${qs}` : path
}

export function isAbort(e: unknown): boolean {
  return typeof e === 'object' && e !== null && (e as { name?: string }).name === 'AbortError'
}

export async function getJson<T>(path: string, params: Params, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(buildUrl(path, params), { signal })
  } catch (e) {
    if (isAbort(e)) throw e
    throw new ApiError('network', '서버에 연결할 수 없음')
  }
  if (res.status === 503) throw new ApiError('db', 'DB 를 찾을 수 없음', 503)
  if (!res.ok) throw new ApiError('http', `HTTP ${res.status}`, res.status)
  try {
    return (await res.json()) as T
  } catch (e) {
    if (isAbort(e)) throw e
    throw new ApiError('http', '응답을 읽을 수 없음', res.status)
  }
}

/** 화면에 보여 줄 오류 문구. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.kind === 'db') return '서버의 DB를 찾을 수 없어요'
    if (e.kind === 'network') return '서버에 연결할 수 없어요. 백엔드(uvicorn)가 실행 중인지 확인해 주세요'
    return `요청에 실패했어요 (${e.message})`
  }
  return '알 수 없는 오류가 발생했어요'
}

export type ProgramQuery = {
  tab: ProgramTab
  q?: string
  category?: string | null
  date?: string | null
  limit: number
  offset?: number
}

export const api = {
  meta: (signal?: AbortSignal) => getJson<Meta>('/api/meta', {}, signal),

  programs: (query: ProgramQuery, signal?: AbortSignal) =>
    getJson<ProgramList>(
      '/api/programs',
      {
        tab: query.tab,
        q: query.q,
        category: query.category,
        date: query.date,
        limit: query.limit,
        offset: query.offset,
      },
      signal,
    ),

  program: (sourceId: string, signal?: AbortSignal) =>
    getJson<ProgramDetail>(`/api/programs/${encodeURIComponent(sourceId)}`, {}, signal),

  changes: (days: number, type?: ChangeType, signal?: AbortSignal) =>
    getJson<ChangeList>('/api/changes', { days, type }, signal),

  calendar: (month: string, q?: string, category?: string | null, signal?: AbortSignal) =>
    getJson<CalendarResponse>('/api/calendar', { month, q, category }, signal),
}
