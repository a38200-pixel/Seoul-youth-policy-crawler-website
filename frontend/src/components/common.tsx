import { errorMessage } from '../api/client'
import type { Badge } from '../api/types'
import { badgeText, badgeTone } from '../lib/changes'

export function Loading({ label = '불러오는 중…' }: { label?: string }) {
  return (
    <p className="state state-loading" role="status">
      {label}
    </p>
  )
}

export function Empty({ text = '조건에 맞는 공고가 없어요' }: { text?: string }) {
  return <p className="state state-empty">{text}</p>
}

export function ErrorView({ error }: { error: unknown }) {
  return (
    <p className="state state-error" role="alert">
      {errorMessage(error)}
    </p>
  )
}

/** 서버가 준 badges 를 그대로 보여 준다(규칙을 새로 만들지 않는다). detail 은 툴팁. */
export function BadgeList({ badges }: { badges: Badge[] }) {
  if (badges.length === 0) return null
  return (
    <span className="badges">
      {badges.map((b) => (
        <span key={b.type} className={`badge badge-${badgeTone(b.type)}`} title={b.detail ?? undefined}>
          {badgeText(b)}
        </span>
      ))}
    </span>
  )
}

export function LoadMore({
  loading,
  error,
  onClick,
}: {
  loading: boolean
  error?: unknown
  onClick: () => void
}) {
  return (
    <div className="more-wrap">
      {error ? <ErrorView error={error} /> : null}
      <button type="button" className="more" onClick={onClick} disabled={loading}>
        {loading ? '불러오는 중…' : '더 보기'}
      </button>
    </div>
  )
}
