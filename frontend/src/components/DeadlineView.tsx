import { useState } from 'react'
import { api } from '../api/client'
import { usePagedPrograms, useRequest } from '../api/hooks'
import type { ProgramQuery } from '../api/client'
import { Empty, ErrorView, LoadMore, Loading } from './common'
import { ProgramCard, ProgramRow } from './ProgramCard'
import type { OpenHandler } from './ProgramCard'

const TODAY_PREVIEW = 4 // 오늘 마감 섹션에 먼저 보여 줄 건수
const SOON_PAGE = 12 // 곧 마감 섹션의 한 번에 불러올 건수
const OPEN_PAGE = 50 // 마감일 미정 섹션의 한 번에 불러올 건수
const API_MAX = 200 // 서버의 limit 상한

type Props = { today: string; q: string; category: string | null; onOpen: OpenHandler }

/**
 * 마감 임박 탭 본문(날짜를 고르지 않았을 때).
 *  1) 오늘 마감: tab=deadline&date=<서버 today>. 응답의 counts.deadline·group_counts.open 도 여기서 얻는다.
 *  2) 마감일 미정: 개수는 group_counts.open, 항목은 tab=deadline&group=open. 개수가 0이면 섹션을 숨긴다.
 *  3) 곧 마감: tab=deadline 정렬(모집중 → 모집예정 → 마감일 미정)에서 오늘 마감 건수만큼 건너뛴 offset 부터,
 *     목록 끝의 미정 항목(group_counts.open 건) 앞까지. 이렇게 구간을 잘라 미정 항목과 겹치지 않으면서 모집예정은 그대로 보인다.
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
  const openCount = first.status === 'ok' ? first.data.group_counts.open : 0

  const full = useRequest(
    expanded && todayTotal > TODAY_PREVIEW
      ? (signal) => api.programs({ ...base, date: today, limit: Math.min(todayTotal, API_MAX) }, signal)
      : null,
    `todayFull|${filterKey}|${expanded}|${todayTotal}`,
  )

  const open = usePagedPrograms({
    enabled: first.status === 'ok' && openCount > 0,
    query: { ...base, group: 'open' },
    startOffset: 0,
    pageSize: OPEN_PAGE,
  })

  const soon = usePagedPrograms({
    enabled: first.status === 'ok' && deadlineTotal > 0,
    query: base,
    startOffset: todayTotal,
    pageSize: SOON_PAGE,
    endOffset: deadlineTotal - openCount,
  })

  if (first.status === 'loading' || first.status === 'idle') return <Loading />
  if (first.status === 'error') return <ErrorView error={first.error} />
  if (deadlineTotal === 0) return <Empty />

  const todayItems = expanded && full.status === 'ok' ? full.data.items : first.data.items

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
        {soon.status === 'loading' || soon.status === 'idle' ? <Loading /> : null}
        {soon.status === 'error' ? <ErrorView error={soon.error} /> : null}
        {soon.status === 'ok' && soon.items.length === 0 ? (
          <Empty text={todayTotal > 0 ? '오늘 이후에 마감하는 공고가 없어요' : '조건에 맞는 공고가 없어요'} />
        ) : null}
        {soon.items.length > 0 ? (
          <ul className="card-grid">
            {soon.items.map((p) => (
              <ProgramCard key={p.source_id} program={p} onOpen={onOpen} />
            ))}
          </ul>
        ) : null}
        {soon.hasMore ? <LoadMore loading={soon.moreLoading} error={soon.moreError} onClick={soon.loadMore} /> : null}
      </section>

      {openCount > 0 ? (
        <section aria-label="마감일 미정">
          <h2 className="section-title">
            마감일 미정 <span className="section-count">{openCount}건</span>
          </h2>
          {open.status === 'loading' || open.status === 'idle' ? <Loading /> : null}
          {open.status === 'error' ? <ErrorView error={open.error} /> : null}
          {open.items.length > 0 ? (
            <ul className="rows">
              {open.items.map((p) => (
                <ProgramRow key={p.source_id} program={p} onOpen={onOpen} />
              ))}
            </ul>
          ) : null}
          {open.hasMore ? <LoadMore loading={open.moreLoading} error={open.moreError} onClick={open.loadMore} /> : null}
        </section>
      ) : null}
    </>
  )
}
