import { useState } from 'react'
import { api } from '../api/client'
import { useRequest } from '../api/hooks'
import type { AsyncState } from '../api/hooks'
import type { ChangeItem, ChangeList, ChangeType } from '../api/types'
import { CHANGE_FILTERS, eventLabel, formatChange } from '../lib/changes'
import { formatShortDateTime } from '../lib/dates'
import { Empty, ErrorView, Loading } from './common'
import type { OpenHandler } from './ProgramCard'

const CHANGE_DAYS = 7
const VISIBLE_STEP = 50

/** 사이드바의 '최근 7일 변경' 카드. /api/changes?days=7 의 counts 를 그대로 보여 준다. */
export function ChangesSummary({ state, onViewAll }: { state: AsyncState<ChangeList>; onViewAll: () => void }) {
  const counts = state.status === 'ok' ? state.data.counts : {}
  const n = (t: ChangeType) => counts[t] ?? 0
  const rows: { label: string; value: number }[] = [
    { label: '신규', value: n('new') },
    { label: '목록에서 내려감', value: n('deactivated') },
    {
      label: '표기 변경 (연장·단축 등)',
      value: n('status_changed') + n('period_changed') + n('extended') + n('shortened'),
    },
  ]
  if (n('reactivated') > 0) rows.push({ label: '다시 게시됨', value: n('reactivated') })
  return (
    <section className="card-side" aria-label="최근 7일 변경">
      <h2 className="side-title">최근 {CHANGE_DAYS}일 변경</h2>
      {state.status === 'loading' ? <Loading /> : null}
      {state.status === 'error' ? <ErrorView error={state.error} /> : null}
      {state.status === 'ok' ? (
        <ul className="summary-list">
          {rows.map((r) => (
            <li key={r.label}>
              <span>{r.label}</span>
              <strong>{r.value}</strong>
            </li>
          ))}
        </ul>
      ) : null}
      <button type="button" className="link-btn block" onClick={onViewAll}>
        변경 이력 전체 보기
      </button>
    </section>
  )
}

function mergeChanges(lists: ChangeList[]): { items: ChangeItem[]; total: number } {
  const items = lists.flatMap((l) => l.items)
  items.sort((a, b) => Date.parse(b.detected_at) - Date.parse(a.detected_at)) // 서버가 준 시각끼리 비교(브라우저 시계 아님)
  return { items, total: items.length }
}

function eventTone(type: ChangeType): string {
  if (type === 'new') return 'new'
  if (type === 'extended') return 'up'
  if (type === 'shortened') return 'down'
  return 'status'
}

/** 최근 변경 탭. 유형 칩이 type 파라미터(복수 유형 칩은 유형별로 요청해 합친다). */
export function ChangesView({ onOpen }: { onOpen: OpenHandler }) {
  const [filterId, setFilterId] = useState('all')
  const [visible, setVisible] = useState(VISIBLE_STEP)
  const filter = CHANGE_FILTERS.find((f) => f.id === filterId) ?? CHANGE_FILTERS[0]

  const state = useRequest(async (signal) => {
    if (filter.types.length === 0) return mergeChanges([await api.changes(CHANGE_DAYS, undefined, signal)])
    return mergeChanges(await Promise.all(filter.types.map((t) => api.changes(CHANGE_DAYS, t, signal))))
  }, `changes|${filterId}`)

  const choose = (id: string) => {
    setFilterId(id)
    setVisible(VISIBLE_STEP)
  }

  return (
    <section aria-label="최근 변경">
      <div className="chips" role="group" aria-label="변경 유형">
        {CHANGE_FILTERS.map((f) => (
          <button key={f.id} type="button" className="chip" aria-pressed={filterId === f.id} onClick={() => choose(f.id)}>
            {f.label}
          </button>
        ))}
      </div>
      {state.status === 'loading' ? <Loading /> : null}
      {state.status === 'error' ? <ErrorView error={state.error} /> : null}
      {state.status === 'ok' && state.data.items.length === 0 ? <Empty text="최근 7일 동안 변경이 없어요" /> : null}
      {state.status === 'ok' && state.data.items.length > 0 ? (
        <>
          <h2 className="section-title">
            최근 {CHANGE_DAYS}일 변경 <span className="section-count">{state.data.total}건</span>
          </h2>
          <ul className="events">
            {state.data.items.slice(0, visible).map((e) => {
              const change = formatChange(e.type, e.old_value, e.new_value)
              return (
                <li key={`${e.type}|${e.source_id}|${e.detected_at}|${e.id ?? ''}`}>
                  <button type="button" className="event-row" onClick={(ev) => onOpen(e.source_id, ev.currentTarget)}>
                    <span className={`badge badge-${eventTone(e.type)}`}>{eventLabel(e.type, e.reason)}</span>
                    <span className="event-title">{e.title ?? e.source_id}</span>
                    <span className="event-date">{formatShortDateTime(e.detected_at)}</span>
                    {change ? <span className="event-change">{change}</span> : null}
                  </button>
                </li>
              )
            })}
          </ul>
          {visible < state.data.items.length ? (
            <div className="more-wrap">
              <button type="button" className="more" onClick={() => setVisible((v) => v + VISIBLE_STEP)}>
                더 보기
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  )
}
