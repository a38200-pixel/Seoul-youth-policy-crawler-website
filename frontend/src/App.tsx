import { useCallback, useRef, useState } from 'react'
import { api } from './api/client'
import { useRequest } from './api/hooks'
import type { Meta } from './api/types'
import { Calendar } from './components/Calendar'
import { ChangesSummary, ChangesView } from './components/ChangesPanels'
import { ErrorView, Loading } from './components/common'
import { DeadlineView } from './components/DeadlineView'
import { DetailPanel } from './components/DetailPanel'
import { Header } from './components/Header'
import { PagedCards } from './components/PagedCards'
import { TabBar } from './components/TabBar'
import type { TabId } from './components/TabBar'
import { formatKoreanDay, monthOf } from './lib/dates'

const noop = () => {}
const CATEGORY_PAGE = 200 // 서버 limit 상한

/**
 * 분야 칩의 목록. /api/meta 에 분야 목록이 없어서 /api/programs?tab=all 을 끝까지 읽어 category 값을 모은다(많이 나온 순).
 * (분야가 비어 있는 상시-기타 공고는 tab=all 에 없으므로 칩에도 없다.)
 */
async function loadCategories(signal: AbortSignal): Promise<string[]> {
  const freq = new Map<string, number>()
  let offset = 0
  for (;;) {
    const r = await api.programs({ tab: 'all', limit: CATEGORY_PAGE, offset }, signal)
    for (const p of r.items) if (p.category) freq.set(p.category, (freq.get(p.category) ?? 0) + 1)
    offset += r.items.length
    if (r.items.length === 0 || offset >= r.total) break
  }
  return [...freq.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ko')).map(([name]) => name)
}

function Main({ meta }: { meta: Meta }) {
  const [tab, setTab] = useState<TabId>('deadline')
  const [q, setQ] = useState('')
  const [category, setCategory] = useState<string | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [month, setMonth] = useState<string>(() => monthOf(meta.today) ?? meta.today.slice(0, 7))
  const [dateTotal, setDateTotal] = useState<number | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const openerRef = useRef<HTMLElement | null>(null)

  const countsState = useRequest(
    (signal) => api.programs({ tab: 'deadline', q, category, limit: 1 }, signal),
    `counts|${q}|${category ?? ''}`,
  )
  const changes7 = useRequest((signal) => api.changes(7, undefined, signal), 'changes7')
  const categories = useRequest(loadCategories, 'categories')

  const openDetail = useCallback((id: string, opener: HTMLElement) => {
    openerRef.current = opener
    setOpenId(id)
  }, [])
  const closeDetail = useCallback(() => {
    setOpenId(null)
    // 닫히면 원래 카드로 포커스를 돌려준다.
    setTimeout(() => {
      const opener = openerRef.current
      if (opener && opener.isConnected) opener.focus()
    }, 0)
  }, [])
  const selectDate = useCallback((date: string | null) => {
    setSelectedDate(date)
    setDateTotal(null)
  }, [])

  const filter = { q, category }

  return (
    <div className="page">
      <Header today={meta.today} lastCollectedAt={meta.last_collected_at} onQuery={setQ} />
      <TabBar
        tab={tab}
        onTab={setTab}
        counts={countsState.status === 'ok' ? countsState.data.counts : null}
        changesTotal={changes7.status === 'ok' ? changes7.data.total : null}
        categories={categories.status === 'ok' ? categories.data : []}
        category={category}
        onCategory={setCategory}
      />
      <div className="layout">
        <main className="main">
          {tab === 'deadline' && selectedDate ? (
            <section aria-label="선택한 날짜의 마감">
              <h2 className="section-title">
                {formatKoreanDay(selectedDate)} 마감
                {dateTotal !== null ? <span className="section-count">{dateTotal}건</span> : null}
              </h2>
              <PagedCards
                query={{ tab: 'deadline', ...filter, date: selectedDate }}
                onOpen={openDetail}
                onTotal={setDateTotal}
              />
            </section>
          ) : null}
          {tab === 'deadline' && !selectedDate ? (
            <DeadlineView key={`${q}|${category ?? ''}`} today={meta.today} q={q} category={category} onOpen={openDetail} />
          ) : null}
          {tab === 'always' ? <PagedCards query={{ tab: 'always', ...filter }} onOpen={openDetail} /> : null}
          {tab === 'etc' ? <PagedCards query={{ tab: 'etc', ...filter }} onOpen={openDetail} /> : null}
          {tab === 'changes' ? <ChangesView onOpen={openDetail} /> : null}
        </main>
        <aside className="sidebar">
          {tab === 'deadline' ? (
            <Calendar
              today={meta.today}
              month={month}
              onMonth={setMonth}
              q={q}
              category={category}
              selected={selectedDate}
              selectedTotal={dateTotal}
              onSelect={selectDate}
            />
          ) : null}
          <ChangesSummary state={changes7} onViewAll={() => setTab('changes')} />
        </aside>
      </div>
      {openId ? <DetailPanel sourceId={openId} onClose={closeDetail} /> : null}
    </div>
  )
}

export default function App() {
  const meta = useRequest((signal) => api.meta(signal), 'meta')
  if (meta.status === 'ok') return <Main meta={meta.data} />
  return (
    <div className="page">
      <Header today={null} lastCollectedAt={null} onQuery={noop} />
      {meta.status === 'error' ? <ErrorView error={meta.error} /> : <Loading />}
    </div>
  )
}
