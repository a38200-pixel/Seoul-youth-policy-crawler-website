import { useEffect, useState } from 'react'
import { formatDateTime, formatFullDate } from '../lib/dates'

const SEARCH_DEBOUNCE_MS = 300

type HeaderProps = {
  today: string | null
  lastCollectedAt: string | null | undefined
  onQuery: (q: string) => void
}

export function Header({ today, lastCollectedAt, onQuery }: HeaderProps) {
  const [value, setValue] = useState('')

  // 입력이 멈춘 뒤 300ms 후에 q 를 바꾼다(요청 남발 방지).
  useEffect(() => {
    const timer = setTimeout(() => onQuery(value.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [value, onQuery])

  return (
    <header className="header">
      <div className="brand">
        <h1 className="logo">청년 D-Day</h1>
        <p className="subtitle">서울 청년정책 마감 알리미</p>
      </div>
      <label className="search">
        <span className="sr-only">공고 검색</span>
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" focusable="false">
          <circle cx="8.5" cy="8.5" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path d="M13 13l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        <input
          type="search"
          value={value}
          placeholder="제목·기관·분야 검색"
          onChange={(e) => setValue(e.target.value)}
        />
      </label>
      <dl className="server-info">
        <div>
          <dt>서버 오늘</dt>
          <dd>{today ? formatFullDate(today) : '-'}</dd>
        </div>
        <div>
          <dt>마지막 수집</dt>
          <dd>{lastCollectedAt ? formatDateTime(lastCollectedAt) : '기록 없음'}</dd>
        </div>
      </dl>
    </header>
  )
}
