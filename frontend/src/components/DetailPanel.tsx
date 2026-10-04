import { useEffect, useRef } from 'react'
import { api } from '../api/client'
import { useRequest } from '../api/hooks'
import type { ProgramDetail } from '../api/types'
import { eventLabel, formatChange, hasEndDate } from '../lib/changes'
import { formatShortDateTime } from '../lib/dates'
import { DetailCalendarActions } from './CalendarActions'
import { BadgeList, ErrorView, Loading } from './common'

const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'

function Body({ d }: { d: ProgramDetail }) {
  const link = d.apply_url || d.source_url
  return (
    <>
      {!d.is_active ? (
        <p className="notice" role="note">
          게시가 종료된 공고입니다
        </p>
      ) : null}
      <h2 className="panel-title" id="detail-title">
        {d.title}
      </h2>
      <BadgeList badges={d.badges} />
      <dl className="detail-list">
        <div>
          <dt>기관</dt>
          <dd>{d.organization || '-'}</dd>
        </div>
        <div>
          <dt>분야</dt>
          <dd>{d.category || '-'}</dd>
        </div>
        <div>
          <dt>대상</dt>
          <dd>{d.target || '-'}</dd>
        </div>
        <div>
          <dt>신청기간</dt>
          <dd>{d.period_text || '-'}</dd>
        </div>
        <div>
          <dt>사이트 상태</dt>
          <dd>{d.source_status || '-'}</dd>
        </div>
      </dl>
      {link ? (
        <a className="apply-btn" href={link} target="_blank" rel="noopener noreferrer">
          신청 페이지 열기
        </a>
      ) : null}
      <DetailCalendarActions program={d} />

      <h3 className="panel-sub">변경 이력</h3>
      {d.history.length === 0 ? (
        <p className="state state-empty">기록된 변경 이력이 없어요</p>
      ) : (
        <ul className="history">
          {d.history.map((h, i) => {
            const change = formatChange(h.change_type, h.old_value, h.new_value)
            return (
              <li key={`${h.id ?? 'n'}-${i}`}>
                <span className="history-date">{formatShortDateTime(h.detected_at)}</span>
                <span className="history-label">{eventLabel(h.change_type, h.reason, hasEndDate(d.end_date))}</span>
                {change ? <span className="history-change">{change}</span> : null}
              </li>
            )
          })}
        </ul>
      )}
    </>
  )
}

/** 오른쪽에서 열리는 상세 패널(작은 화면은 전체 화면). Esc·바깥 클릭·닫기 버튼으로 닫고, 열릴 때 패널로 포커스를 옮긴다. */
export function DetailPanel({ sourceId, onClose }: { sourceId: string; onClose: () => void }) {
  const state = useRequest((signal) => api.program(sourceId, signal), `detail|${sourceId}`)
  const panelRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    panelRef.current?.focus()
  }, [sourceId])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panelRef.current) return
      const items = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || active === panelRef.current)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="overlay" onClick={onClose}>
      <aside
        ref={panelRef}
        className="panel"
        role="dialog"
        aria-modal="true"
        aria-label="공고 상세"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="panel-close" onClick={onClose}>
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" focusable="false">
            <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          닫기
        </button>
        {state.status === 'loading' || state.status === 'idle' ? <Loading /> : null}
        {state.status === 'error' ? <ErrorView error={state.error} /> : null}
        {state.status === 'ok' ? <Body d={state.data} /> : null}
      </aside>
    </div>
  )
}
