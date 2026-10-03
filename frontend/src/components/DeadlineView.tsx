import { useState } from 'react'
import { api } from '../api/client'
import { usePagedPrograms, useRequest } from '../api/hooks'
import type { ProgramQuery } from '../api/client'
import { Empty, ErrorView, LoadMore, Loading } from './common'
import { ProgramCard, ProgramRow } from './ProgramCard'
import type { OpenHandler } from './ProgramCard'

const TODAY_PREVIEW = 4 // 오늘 마감 섹션에 먼저 보여 줄 건수
const SOON_PAGE = 12 // 곧 마감 섹션의 한 번에 불러올 건수
const API_MAX = 200 // 서버의 limit 상한
const TAIL = 50 // 마감일 미정 항목을 찾으려고 목록 끝에서 읽는 건수

type Props = { today: string; q: string; category: string | null; onOpen: OpenHandler }

/**
 * 마감 임박 탭 본문(날짜를 고르지 않았을 때).
 *  1) 오늘 마감: tab=deadline&date=<서버 today>
 *  2) 마감일 미정: 정렬상 목록 맨 끝(group=open)이므로 끝쪽을 읽어 group 으로 구분
 *  3) 곧 마감: 오늘 마감 건수만큼 건너뛴 offset 부터(오늘 마감이 정렬상 맨 앞이라는 점에 의존), 미정 항목 앞까지
 */
export function DeadlineView({ today, q, category, onOpen }: Props) {
  const base: Omit<ProgramQuery, 'limit' | 'offset'> = { tab: 'deadline', q, category }
  const filterKey = `${today}|${q}|${category ?? ''}`
  const [expanded, setExpanded] = useState(false)

  const first = useRequest(
    (signal) => api.programs({ ...base, date: today, limit: TODAY_PREVIEW }, signal),
    `today|${filterKey}`,
  )
  const todayTotal = first.status === 'ok' ? first.data.total : 0
  const deadlineTotal = first.status === 'ok' ? first.data.counts.deadline : 0

  const full = useRequest(
    expanded && todayTotal > TODAY_PREVIEW
      ? (signal) => api.programs({ ...base, date: today, limit: Math.min(todayTotal, API_MAX) }, signal)
      : null,
    `todayFull|${filterKey}|${expanded}|${todayTotal}`,
  )

  const tail = useRequest(
    first.status === 'ok' && deadlineTotal > 0
      ? (signal) => api.programs({ ...base, limit: TAIL, offset: Math.max(0, deadlineTotal - TAIL) }, signal)
      : null,
    `tail|${filterKey}|${deadlineTotal}`,
  )
  const openItems = tail.status === 'ok' ? tail.data.items.filter((p) => p.group === 'open') : []

  const soon = usePagedPrograms({
    enabled: tail.status === 'ok',
    query: base,
    startOffset: todayTotal,
    pageSize: SOON_PAGE,
    endOffset: deadlineTotal - openItems.length,
  })

  if (first.status === 'loading' || first.status === 'idle') return <Loading />
  if (first.status === 'error') return <ErrorView error={first.error} />
  if (deadlineTotal === 0) return <Empty />

  const todayItems = expanded && full.status === 'ok' ? full.data.items : first.data.items
  const soonItems = soon.items.filter((p) => p.group !== 'open')

  return (
    <>
      {todayTotal > 0 ? (
        <section aria-label="오늘 마감">
          <h2 className="section-title">
            오늘 마감 <span className="section-count">{todayTotal}건</span>
          </h2>
          <ul className="card-grid">
            {todayItems.map((p) => (
              <ProgramCard key={p.source_id} program={p} onOpen={onOpen} />
            ))}
          </ul>
          {expanded && full.status === 'loading' ? <Loading /> : null}
          {expanded && full.status === 'error' ? <ErrorView error={full.error} /> : null}
          {!expanded && todayTotal > TODAY_PREVIEW ? (
            <div className="more-wrap">
              <button type="button" className="more" onClick={() => setExpanded(true)}>
                나머지 {todayTotal - TODAY_PREVIEW}건 펼치기
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      <section aria-label="곧 마감">
        <h2 className="section-title">곧 마감</h2>
        {tail.status === 'loading' || tail.status === 'idle' || soon.status === 'loading' ? <Loading /> : null}
        {tail.status === 'error' ? <ErrorView error={tail.error} /> : null}
        {soon.status === 'error' ? <ErrorView error={soon.error} /> : null}
        {soon.status === 'ok' && soonItems.length === 0 ? (
          <Empty text={todayTotal > 0 ? '오늘 이후에 마감하는 공고가 없어요' : '조건에 맞는 공고가 없어요'} />
        ) : null}
        {soonItems.length > 0 ? (
          <ul className="card-grid">
            {soonItems.map((p) => (
              <ProgramCard key={p.source_id} program={p} onOpen={onOpen} />
            ))}
          </ul>
        ) : null}
        {soon.hasMore ? <LoadMore loading={soon.moreLoading} error={soon.moreError} onClick={soon.loadMore} /> : null}
      </section>

      {openItems.length > 0 ? (
        <section aria-label="마감일 미정">
          <h2 className="section-title">
            마감일 미정 <span className="section-count">{openItems.length}건</span>
          </h2>
          <ul className="rows">
            {openItems.map((p) => (
              <ProgramRow key={p.source_id} program={p} onOpen={onOpen} />
            ))}
          </ul>
        </section>
      ) : null}
    </>
  )
}
