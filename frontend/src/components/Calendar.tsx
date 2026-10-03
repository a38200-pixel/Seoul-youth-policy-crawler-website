import { useMemo } from 'react'
import { api } from '../api/client'
import { useRequest } from '../api/hooks'
import { INTENSITY_LEGEND, buildMonthGrid, intensityLevel } from '../lib/calendar'
import { WEEKDAYS, formatKoreanDay, formatMonthTitle, parseMonth, shiftMonth } from '../lib/dates'
import { ErrorView } from './common'

const MIN_MONTH = '2000-01' // 서버가 받는 연도 범위(2000~2100)
const MAX_MONTH = '2100-12'

type CalendarProps = {
  today: string
  month: string
  onMonth: (month: string) => void
  q: string
  category: string | null
  selected: string | null
  selectedTotal: number | null
  onSelect: (date: string | null) => void
}

export function Calendar({ today, month, onMonth, q, category, selected, selectedTotal, onSelect }: CalendarProps) {
  const state = useRequest(
    (signal) => api.calendar(month, q, category, signal),
    `calendar|${month}|${q}|${category ?? ''}`,
  )
  const counts = useMemo(() => {
    const map = new Map<string, number>()
    if (state.status === 'ok') for (const d of state.data.days) map.set(d.date, d.count)
    return map
  }, [state])
  const serverToday = state.status === 'ok' ? state.data.today : today
  const weeks = useMemo(() => buildMonthGrid(month), [month])
  const monthNumber = parseMonth(month)?.m ?? 0

  return (
    <section className="card-side calendar" aria-label="마감 캘린더">
      <div className="cal-head">
        <button
          type="button"
          className="icon-btn"
          aria-label="이전 달"
          disabled={month <= MIN_MONTH}
          onClick={() => onMonth(shiftMonth(month, -1))}
        >
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" focusable="false">
            <path d="M12.5 4.5L7 10l5.5 5.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
        <h2 className="cal-title">{formatMonthTitle(month)}</h2>
        <button
          type="button"
          className="icon-btn"
          aria-label="다음 달"
          disabled={month >= MAX_MONTH}
          onClick={() => onMonth(shiftMonth(month, 1))}
        >
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" focusable="false">
            <path d="M7.5 4.5L13 10l-5.5 5.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {state.status === 'error' ? <ErrorView error={state.error} /> : null}

      <div className="cal-grid" role="grid" aria-label={`${formatMonthTitle(month)} 마감 달력`} aria-busy={state.status === 'loading'}>
        <div className="cal-row cal-weekdays" role="row">
          {WEEKDAYS.map((w) => (
            <span key={w} className="cal-weekday" role="columnheader">
              {w}
            </span>
          ))}
        </div>
        {weeks.map((week, wi) => (
          <div key={wi} className="cal-row" role="row">
            {week.map((cell, ci) => {
              if (!cell) return <span key={ci} className="cal-cell cal-empty" role="gridcell" />
              const count = counts.get(cell.date) ?? 0
              const past = cell.date < serverToday
              const isToday = cell.date === serverToday
              const isSelected = cell.date === selected
              const level = intensityLevel(count)
              const label =
                `${monthNumber}월 ${cell.day}일` + (count > 0 ? `, ${count}건 마감` : '') + (isToday ? ', 오늘' : '')
              return (
                <span key={ci} className="cal-cell" role="gridcell">
                  <button
                    type="button"
                    className={`cal-day${isToday ? ' is-today' : ''}${isSelected ? ' is-selected' : ''}${past ? ' is-past' : ''}`}
                    aria-label={label}
                    aria-pressed={isSelected}
                    title={count > 0 ? `${count}건 마감` : undefined}
                    disabled={past}
                    onClick={() => onSelect(isSelected ? null : cell.date)}
                  >
                    <span className="cal-num">{cell.day}</span>
                    {level > 0 ? <span className={`cal-dot lvl-${level}`} aria-hidden="true" /> : null}
                  </button>
                </span>
              )
            })}
          </div>
        ))}
      </div>

      <ul className="cal-legend" aria-label="점 색 설명">
        {INTENSITY_LEGEND.map((l) => (
          <li key={l.level}>
            <span className={`cal-dot lvl-${l.level}`} aria-hidden="true" />
            {l.label}
          </li>
        ))}
      </ul>

      {selected ? (
        <p className="cal-selected">
          <span>
            {formatKoreanDay(selected, false)} 선택됨 · 마감 {selectedTotal === null ? '…' : selectedTotal}건
          </span>
          <button type="button" className="link-btn" onClick={() => onSelect(null)}>
            선택 해제
          </button>
        </p>
      ) : null}

      <button type="button" className="ics-btn" disabled title="준비 중">
        내 캘린더에 마감일 추가 (.ics)
      </button>
    </section>
  )
}
