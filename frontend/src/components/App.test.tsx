import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

// 서버 응답을 흉내 낸 목킹 데이터(테스트 전용). 화면 코드에는 샘플 데이터가 없다.
const META = {
  today: '2026-10-03',
  active_count: 6,
  expired_active_count: 0,
  tab_counts: { deadline: 3, always: 2, etc: 1, all: 6 },
  categories: [
    { name: '일자리', count: 56 },
    { name: '주거', count: 36 },
  ],
  last_collected_at: '2026-10-03T07:12:00+09:00',
  window_days: 7,
  events_7d: {},
  new_7d: 0,
  baseline_date: '2026-10-01',
}

const gc = (o: Partial<Record<string, number>> = {}) => ({
  recruiting: 0,
  upcoming: 0,
  open: 0,
  always: 0,
  always_etc: 0,
  unknown: 0,
  ...o,
})

let requested: URL[] = []
let metaStatus = 200
let programsBody: ((url: URL) => unknown) | null = null
let changesBody: (() => unknown) | null = null
let detailBody: (() => unknown) | null = null

function body(url: URL): unknown {
  if (/^\/api\/programs\/[^/]+$/.test(url.pathname)) return detailBody ? detailBody() : {}
  switch (url.pathname) {
    case '/api/meta':
      return META
    case '/api/programs':
      return programsBody
        ? programsBody(url)
        : {
            items: [],
            total: 0,
            counts: { deadline: 3, always: 2, etc: 1 },
            group_counts: gc({ recruiting: 3, always: 2, always_etc: 1 }),
          }
    case '/api/changes':
      return changesBody ? changesBody() : { days: 7, total: 0, counts: {}, items: [] }
    case '/api/calendar':
      return { month: url.searchParams.get('month'), today: '2026-10-03', days: [{ date: '2026-10-06', count: 26 }] }
    default:
      return {}
  }
}

const calls = (pathname: string) => requested.filter((u) => u.pathname === pathname)
const has = (pathname: string, params: Record<string, string>) =>
  calls(pathname).some((u) => Object.entries(params).every(([k, v]) => u.searchParams.get(k) === v))

beforeEach(() => {
  requested = []
  metaStatus = 200
  programsBody = null
  changesBody = null
  detailBody = null
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      requested.push(url)
      const status = url.pathname === '/api/meta' ? metaStatus : 200
      return new Response(JSON.stringify(status === 200 ? body(url) : { detail: 'x' }), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('App 요청 URL', () => {
  it('처음에는 서버 today 로 오늘 마감을, 이번 달 캘린더를 요청한다', async () => {
    render(<App />)
    await waitFor(() => expect(has('/api/programs', { tab: 'deadline', date: '2026-10-03', limit: '4' })).toBe(true))
    await waitFor(() => expect(has('/api/calendar', { month: '2026-10' })).toBe(true))
  })

  it('탭을 바꾸면 그 탭의 tab 파라미터로 요청한다', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /^상시/ }))
    await waitFor(() => expect(has('/api/programs', { tab: 'always', limit: '24', offset: '0' })).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: /^기타/ }))
    await waitFor(() => expect(has('/api/programs', { tab: 'etc' })).toBe(true))
    // 상시 탭에서는 캘린더가 숨겨진다
    expect(screen.queryByLabelText('마감 캘린더')).toBeNull()
  })

  it('날짜를 선택하면 date 파라미터로 단일 목록을 요청하고, 다시 누르면 해제된다', async () => {
    render(<App />)
    const day = await screen.findByRole('button', { name: '10월 6일, 26건 마감' })
    expect(day.getAttribute('title')).toBe('26건 마감') // 색만으로 전달하지 않는다
    fireEvent.click(day)
    await waitFor(() => expect(has('/api/programs', { tab: 'deadline', date: '2026-10-06', limit: '24' })).toBe(true))
    expect(await screen.findByText(/10월 6일 선택됨/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '10월 6일, 26건 마감' }))
    await waitFor(() => expect(screen.queryByText(/선택됨/)).toBeNull())
  })

  it('오늘 이전 날짜는 비활성이다', async () => {
    render(<App />)
    const past = await screen.findByRole('button', { name: '10월 2일' })
    expect((past as HTMLButtonElement).disabled).toBe(true)
  })

  it('최근 변경 탭의 유형 칩은 type 파라미터로 요청한다(연장·단축은 둘 다)', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /^최근 변경/ }))
    fireEvent.click(await screen.findByRole('button', { name: '목록에서 내려감' }))
    await waitFor(() => expect(has('/api/changes', { days: '7', type: 'deactivated' })).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: '마감 연장·단축' }))
    await waitFor(() => {
      expect(has('/api/changes', { days: '7', type: 'extended' })).toBe(true)
      expect(has('/api/changes', { days: '7', type: 'shortened' })).toBe(true)
    })
  })
})

describe('분야 칩', () => {
  it('/api/meta 의 categories 에서 오고, tab=all 전체 읽기를 하지 않는다', async () => {
    render(<App />)
    expect(await screen.findByRole('button', { name: '일자리' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '주거' })).toBeTruthy()
    await waitFor(() => expect(has('/api/programs', { tab: 'deadline', date: '2026-10-03' })).toBe(true))
    expect(calls('/api/meta')).toHaveLength(1) // 최초 1회 요청 1번
    expect(has('/api/programs', { tab: 'all' })).toBe(false)
  })

  it('칩을 누르면 category 파라미터로 요청한다', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '주거' }))
    await waitFor(() => expect(has('/api/programs', { tab: 'deadline', category: '주거', date: '2026-10-03' })).toBe(true))
  })
})

describe('마감일 미정 섹션 (group_counts.open 기준)', () => {
  const program = (id: string, group: string, title: string) => ({
    source_id: id,
    title,
    category: null,
    organization: null,
    display_status: group === 'open' ? '마감일 미정' : '모집중',
    group,
    d_day: group === 'open' ? null : 5,
    d_day_label: group === 'open' ? null : 'D-5',
    source_status: '모집중',
    period_text: null,
    start_date: null,
    end_date: group === 'open' ? null : '2026-10-08',
    apply_url: null,
    source_url: null,
    first_seen_at: null,
    badges: [],
  })

  it('group_counts.open 이 1 이상이면 group=open 으로 항목을 가져와 보여 주고, 곧 마감에는 나오지 않는다', async () => {
    const recruiting = [program('1', 'recruiting', '마감 임박 공고 A'), program('2', 'recruiting', '마감 임박 공고 B')]
    const open = [program('3', 'open', '마감일 미정 공고 C')]
    programsBody = (url) => {
      const counts = { deadline: 3, always: 0, etc: 0 }
      const group_counts = gc({ recruiting: 2, open: 1 })
      if (url.searchParams.get('group') === 'open') return { items: open, total: 1, counts, group_counts }
      if (url.searchParams.get('date')) return { items: [], total: 0, counts, group_counts } // 오늘 마감 없음
      const offset = Number(url.searchParams.get('offset') ?? 0)
      const limit = Number(url.searchParams.get('limit'))
      return { items: [...recruiting, ...open].slice(offset, offset + limit), total: 3, counts, group_counts }
    }
    render(<App />)
    expect(await screen.findByText('마감일 미정 공고 C')).toBeTruthy()
    const openSection = screen.getByLabelText('마감일 미정')
    expect(openSection.textContent).toContain('1건') // 개수는 group_counts.open
    await waitFor(() => expect(screen.getByLabelText('곧 마감').textContent).toContain('마감 임박 공고 B'))
    const soon = screen.getByLabelText('곧 마감')
    expect(soon.textContent).toContain('마감 임박 공고 A')
    expect(soon.textContent).not.toContain('마감일 미정 공고 C')
    expect(has('/api/programs', { tab: 'deadline', group: 'open' })).toBe(true)
    // 목록 끝을 훑어 미정을 찾는 요청(group 없이 limit=50)은 더 이상 없다
    expect(requested.some((u) => u.pathname === '/api/programs' && !u.searchParams.has('group') && u.searchParams.get('limit') === '50')).toBe(false)
  })

  it('group_counts.open 이 0 이면 섹션도 group=open 요청도 없다', async () => {
    const all = [program('1', 'recruiting', '마감 임박 공고 A')]
    programsBody = (url) => {
      const counts = { deadline: 1, always: 0, etc: 0 }
      const group_counts = gc({ recruiting: 1 })
      if (url.searchParams.get('date')) return { items: [], total: 0, counts, group_counts }
      return { items: all, total: 1, counts, group_counts }
    }
    render(<App />)
    expect(await screen.findByText('마감 임박 공고 A')).toBeTruthy()
    expect(screen.queryByLabelText('마감일 미정')).toBeNull()
    expect(has('/api/programs', { group: 'open' })).toBe(false)
  })
})

describe('최근 변경 탭 문구', () => {
  const change = (id: number, reason: string, endDate: string | null, title: string) => ({
    id,
    type: 'deactivated',
    source_id: String(id),
    title,
    detected_at: '2026-10-03T07:00:00+09:00',
    old_value: '1',
    new_value: '0',
    reason,
    end_date: endDate,
    period_type: endDate ? 'dated' : 'always',
  })

  it('deactivated 문구는 reason 과 end_date 로 갈린다', async () => {
    changesBody = () => ({
      days: 7,
      total: 3,
      counts: { deactivated: 3 },
      items: [
        change(1, 'expired', '2026-10-02', '만료된 공고'),
        change(2, 'early', '2026-10-20', '마감일 전에 내려간 공고'),
        change(3, 'early', null, '상시였던 공고'),
      ],
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /^최근 변경/ }))
    expect(await screen.findByText('마감됨')).toBeTruthy()
    expect(screen.getByText('마감일 전에 목록에서 내려감')).toBeTruthy()
    expect(screen.getByText('게시 종료')).toBeTruthy()
    expect(screen.getByText('전체 3건 중 3건 표시')).toBeTruthy()
  })

  it('전체 N건 중 M건 표시: 50건씩 늘어난다', async () => {
    changesBody = () => ({
      days: 7,
      total: 60,
      counts: { deactivated: 60 },
      items: Array.from({ length: 60 }, (_, i) => change(i + 1, 'expired', '2026-10-02', `공고 ${i + 1}`)),
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /^최근 변경/ }))
    expect(await screen.findByText('전체 60건 중 50건 표시')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '더 보기' }))
    expect(await screen.findByText('전체 60건 중 60건 표시')).toBeTruthy()
  })
})

describe('구글 캘린더에 추가: 상세 패널 버튼', () => {
  const NOTE = '추가한 시점의 마감일 기준이며 이후 변경은 자동 반영되지 않습니다'
  const card = {
    source_id: 'p1',
    title: '오늘 마감 공고',
    category: '금융',
    organization: '서울시',
    display_status: '모집중',
    group: 'recruiting',
    d_day: 0,
    d_day_label: 'D-Day',
    source_status: '모집중',
    period_text: '2026-09-29 ~ 2026-10-03',
    start_date: '2026-09-29',
    end_date: '2026-10-03',
    apply_url: null,
    source_url: 'https://youth.seoul.go.kr/infoData/sprtInfo/view.do?sprtInfoId=1&key=2',
    first_seen_at: null,
    badges: [],
    calendar_exportable: true,
  }
  const gc = { recruiting: 1, upcoming: 0, open: 0, always: 0, always_etc: 0, unknown: 0 }

  function setup(detail: Record<string, unknown>) {
    programsBody = (url) => {
      const counts = { deadline: 1, always: 0, etc: 0 }
      if (url.searchParams.get('date')) return { items: [card], total: 1, counts, group_counts: gc }
      return { items: [], total: 1, counts, group_counts: gc }
    }
    detailBody = () => ({ ...card, summary: null, target: null, schedule_text: null, is_active: true, history: [], ...detail })
  }

  async function openDetail() {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /오늘 마감 공고/ }))
    return within(await screen.findByRole('dialog', { name: '공고 상세' }))
  }

  it('calendar_exportable 이 true 이면 구글 캘린더 링크와 안내 한 줄만 보인다', async () => {
    setup({})
    const dialog = await openDetail()
    const google = await dialog.findByRole('link', { name: '구글 캘린더에 추가' })
    const href = google.getAttribute('href')!
    expect(href.startsWith('https://calendar.google.com/calendar/render?')).toBe(true)
    expect(google.getAttribute('target')).toBe('_blank')
    expect(google.getAttribute('rel')).toBe('noopener noreferrer')
    const p = new URL(href).searchParams
    expect(p.get('text')).toBe('[마감] 오늘 마감 공고')
    expect(p.get('dates')).toBe('20261003/20261004') // 마감일/마감일+1일
    expect(p.get('details')).toContain('기관: 서울시')
    expect(dialog.getByText(NOTE)).toBeTruthy()
    expect(within(dialog.getByLabelText('캘린더에 추가')).getAllByRole('link')).toHaveLength(1) // 링크는 구글 버튼 하나뿐
  })

  it('연말 마감은 구글 링크의 dates 가 다음 해 1월 1일로 끝난다', async () => {
    setup({ end_date: '2026-12-31' })
    const dialog = await openDetail()
    const href = (await dialog.findByRole('link', { name: '구글 캘린더에 추가' })).getAttribute('href')!
    expect(new URL(href).searchParams.get('dates')).toBe('20261231/20270101')
  })

  it('calendar_exportable 이 false 이면 버튼과 안내가 모두 없다', async () => {
    setup({ calendar_exportable: false })
    const dialog = await openDetail()
    await dialog.findByText('오늘 마감 공고')
    expect(dialog.queryByRole('link', { name: '구글 캘린더에 추가' })).toBeNull()
    expect(dialog.queryByText(NOTE)).toBeNull()
  })

  it('서버가 true 라도 마감일이 없으면 버튼을 보여 주지 않는다', async () => {
    setup({ end_date: null })
    const dialog = await openDetail()
    await dialog.findByText('오늘 마감 공고')
    expect(dialog.queryByRole('link', { name: '구글 캘린더에 추가' })).toBeNull()
    expect(dialog.queryByText(NOTE)).toBeNull()
  })
})

describe('달력 사이드바', () => {
  it('달력 아래에 목록 내보내기 버튼·안내가 없고, 달력과 최근 변경 카드는 그대로 있다', async () => {
    render(<App />)
    await screen.findByRole('button', { name: '10월 6일, 26건 마감' })
    expect(screen.queryByText(/내보내기/)).toBeNull()
    expect(screen.queryByText(/앞 100건/)).toBeNull()
    expect(screen.getByLabelText('마감 캘린더')).toBeTruthy()
    expect(screen.getByLabelText('최근 7일 변경')).toBeTruthy()
    // 파일 내보내기용 요청도 하지 않는다
    expect(requested.some((u) => u.pathname.includes('export'))).toBe(false)
  })
})

describe('오류 상태', () => {
  it('503 이면 DB 를 찾을 수 없다는 문구를 보여 준다', async () => {
    metaStatus = 503
    render(<App />)
    expect(await screen.findByText('서버의 DB를 찾을 수 없어요')).toBeTruthy()
  })

  it('네트워크 오류면 백엔드 실행 안내를 보여 준다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
    render(<App />)
    expect(await screen.findByText(/서버에 연결할 수 없어요\. 백엔드\(uvicorn\)가 실행 중인지 확인해 주세요/)).toBeTruthy()
  })
})
