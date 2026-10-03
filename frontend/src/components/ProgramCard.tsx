import type { Program } from '../api/types'
import { ddayTone, deadlineLine } from '../lib/deadline'
import { BadgeList } from './common'

export type OpenHandler = (sourceId: string, opener: HTMLElement) => void

/** 카드 전체가 버튼이다. D-Day 라벨은 서버가 준 d_day_label 을 그대로 쓴다(상시처럼 없으면 표시 상태). */
export function ProgramCard({ program: p, onOpen }: { program: Program; onOpen: OpenHandler }) {
  const tone = ddayTone(p)
  const line = deadlineLine(p) ?? p.period_text ?? p.display_status
  return (
    <li>
      <button type="button" className="card" onClick={(e) => onOpen(p.source_id, e.currentTarget)}>
        <span className="card-top">
          <span className={`dday dday-${tone}`}>{p.d_day_label ?? p.display_status}</span>
          {p.category ? <span className="chip-static">{p.category}</span> : null}
        </span>
        <span className="card-title">{p.title}</span>
        <span className="card-org">{p.organization ?? ''}</span>
        <span className="card-foot">
          <span className="deadline">{line}</span>
          <BadgeList badges={p.badges} />
        </span>
      </button>
    </li>
  )
}

/** 마감일 미정처럼 한 줄로 보여 주는 행. */
export function ProgramRow({ program: p, onOpen }: { program: Program; onOpen: OpenHandler }) {
  return (
    <li>
      <button type="button" className="row" onClick={(e) => onOpen(p.source_id, e.currentTarget)}>
        <span className="row-title">{p.title}</span>
        <span className="row-org">{p.organization ?? ''}</span>
        {p.category ? <span className="chip-static">{p.category}</span> : null}
        <span className="row-status">{p.display_status}</span>
        <BadgeList badges={p.badges} />
      </button>
    </li>
  )
}
