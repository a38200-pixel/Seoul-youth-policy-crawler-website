import type { TabCounts } from '../api/types'

export type TabId = 'deadline' | 'always' | 'etc' | 'changes'

const TABS: { id: TabId; label: string }[] = [
  { id: 'deadline', label: '마감 임박' },
  { id: 'always', label: '상시' },
  { id: 'etc', label: '기타' },
  { id: 'changes', label: '최근 변경' },
]

type TabBarProps = {
  tab: TabId
  onTab: (tab: TabId) => void
  counts: TabCounts | null
  changesTotal: number | null
  categories: string[]
  category: string | null
  onCategory: (category: string | null) => void
}

export function TabBar({ tab, onTab, counts, changesTotal, categories, category, onCategory }: TabBarProps) {
  const countOf = (id: TabId): number | null => (id === 'changes' ? changesTotal : counts ? counts[id] : null)
  return (
    <div className="tabbar">
      <div className="tabs" role="group" aria-label="목록 종류">
        {TABS.map(({ id, label }) => {
          const n = countOf(id)
          return (
            <button key={id} type="button" className="tab" aria-pressed={tab === id} onClick={() => onTab(id)}>
              {label}
              {n !== null ? <span className="tab-count">{n}</span> : null}
            </button>
          )
        })}
      </div>
      <div className="chips" role="group" aria-label="분야">
        <button type="button" className="chip" aria-pressed={category === null} onClick={() => onCategory(null)}>
          전체
        </button>
        {categories.map((c) => (
          <button key={c} type="button" className="chip" aria-pressed={category === c} onClick={() => onCategory(c)}>
            {c}
          </button>
        ))}
      </div>
    </div>
  )
}
