import { useEffect } from 'react'
import { usePagedPrograms } from '../api/hooks'
import type { ProgramQuery } from '../api/client'
import { Empty, ErrorView, LoadMore, Loading } from './common'
import { ProgramCard } from './ProgramCard'
import type { OpenHandler } from './ProgramCard'

const PAGE_SIZE = 24

/** 한 조건의 카드 목록(더 보기로 이어 붙임). 상시·기타 탭과 날짜 선택 목록이 쓴다. */
export function PagedCards({
  query,
  onOpen,
  onTotal,
}: {
  query: Omit<ProgramQuery, 'limit' | 'offset'>
  onOpen: OpenHandler
  onTotal?: (total: number | null) => void
}) {
  const paged = usePagedPrograms({ enabled: true, query, startOffset: 0, pageSize: PAGE_SIZE })

  useEffect(() => {
    onTotal?.(paged.status === 'ok' ? paged.total : null)
  }, [paged.status, paged.total, onTotal])

  if (paged.status === 'loading' || paged.status === 'idle') return <Loading />
  if (paged.status === 'error') return <ErrorView error={paged.error} />
  if (paged.items.length === 0) return <Empty />
  return (
    <>
      <ul className="card-grid">
        {paged.items.map((p) => (
          <ProgramCard key={p.source_id} program={p} onOpen={onOpen} />
        ))}
      </ul>
      {paged.hasMore ? <LoadMore loading={paged.moreLoading} error={paged.moreError} onClick={paged.loadMore} /> : null}
    </>
  )
}
