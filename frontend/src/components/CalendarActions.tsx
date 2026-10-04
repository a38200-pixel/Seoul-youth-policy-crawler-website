import type { ProgramDetail } from '../api/types'
import { IMPORT_NOTE, googleCalendarUrl } from '../lib/calendarExport'

/**
 * 상세 패널의 '구글 캘린더에 추가' 버튼(새 탭). 서버가 준 calendar_exportable 이 true 이고 마감일이 있을 때만 보인다.
 * 링크는 마감일/마감일+1일의 종일 일정이며, 바로 아래에 추가한 시점의 마감일 기준이라는 안내를 한 줄 보여 준다.
 */
export function DetailCalendarActions({ program }: { program: ProgramDetail }) {
  if (!program.calendar_exportable || !program.end_date) return null
  const google = googleCalendarUrl({
    title: program.title,
    endDate: program.end_date,
    organization: program.organization,
    sourceUrl: program.source_url,
  })
  if (!google) return null
  return (
    <section className="cal-actions" aria-label="캘린더에 추가">
      <div className="cal-actions-row">
        <a className="apply-btn secondary" href={google} target="_blank" rel="noopener noreferrer">
          구글 캘린더에 추가
        </a>
      </div>
      <p className="export-note">{IMPORT_NOTE}</p>
    </section>
  )
}
