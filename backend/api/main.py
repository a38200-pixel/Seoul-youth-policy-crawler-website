"""읽기 전용 API. 실행: uvicorn backend.api.main:app --reload

- DB 는 요청마다 file:...?mode=ro 로 열고(환경변수 YOUTH_DB_PATH, 기본 backend/data/youth.db) 쓰지 않는다. 쓰기 엔드포인트는 없다.
- 표시 계산(D-Day·그룹·정렬·배지)은 backend/service/display.py 의 함수를 그대로 쓴다(규칙을 여기서 다시 구현하지 않는다).
- today 는 의존성 get_today 로 주입한다(테스트에서 고정 가능). 기본값은 Asia/Seoul 오늘.
"""
import re
import sqlite3
from collections import Counter
from datetime import date as date_type
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import queries
from backend.crawler.db import BASELINE_DATE, is_new
from backend.crawler.normalizer import today_kst
from backend.service import display as rules
from backend.service.display import badges, compute_display, deadline_on, end_date_of, sort_programs

RECENT_DAYS = 7   # 배지·meta 의 '최근' 기준(일)
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# 탭 → 표시 그룹. 그룹 이름과 의미는 display.py 의 상수가 정의한다.
TAB_GROUPS = {
    "deadline": frozenset({rules.GROUP_RECRUITING, rules.GROUP_UPCOMING, rules.GROUP_OPEN}),
    "always": frozenset({rules.GROUP_ALWAYS}),
    "etc": frozenset({rules.GROUP_ALWAYS_ETC}),
}
Tab = Literal["deadline", "always", "etc", "all"]   # all: unknown 포함, expired 제외(sort_programs 가 expired 를 뺀다)
ChangeType = Literal["new", "extended", "shortened", "period_changed", "status_changed", "deactivated", "reactivated"]

app = FastAPI(title="서울 청년정책 마감 D-Day API (읽기 전용)", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET"], allow_headers=["*"])


# ---------------------------------------------------------------- 의존성
def get_today():
    """오늘(Asia/Seoul 날짜). 테스트에서는 app.dependency_overrides[get_today] 로 고정한다."""
    return today_kst()


def get_conn():
    """요청마다 DB 를 읽기 전용으로 열고 끝나면 닫는다. DB 가 없으면 만들지 않고 503."""
    try:
        conn = queries.connect_readonly()
    except queries.DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    try:
        yield conn
    finally:
        conn.close()


@app.exception_handler(sqlite3.DatabaseError)
def database_error_handler(request, exc):
    """파일이 DB 가 아니거나 스키마가 맞지 않아 쿼리가 실패해도 503 으로 응답한다(DB 는 건드리지 않는다)."""
    return JSONResponse(status_code=503, content={"detail": f"DB 조회에 실패했다: {exc}"})


# ---------------------------------------------------------------- 응답 만들기
def _item(row, display, badge_list):
    return {
        "source_id": row["source_id"],
        "title": row["title"],
        "category": row["category"],
        "organization": row["organization"],
        "display_status": display["display_status"],
        "group": display["group"],
        "d_day": display["d_day"],
        "d_day_label": display["d_day_label"],
        "source_status": display["source_status"],
        "period_text": row["period_text"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "apply_url": row["apply_url"],
        "source_url": row["source_url"],
        "first_seen_at": row["first_seen_at"],
        "badges": badge_list,
    }


def _history_item(e):
    return {"id": e["id"], "change_type": e["change_type"], "old_value": e["old_value"],
            "new_value": e["new_value"], "reason": e["reason"], "detected_at": e["detected_at"]}


def _matches(row, q, category):
    if category and (row["category"] or "") != category:
        return False
    needle = (q or "").strip().lower()
    if needle:
        return any(needle in str(row[k] or "").lower() for k in ("title", "organization", "category"))
    return True


def _tab_counts(pairs):
    return {name: sum(1 for _, d in pairs if d["group"] in groups) for name, groups in TAB_GROUPS.items()}


# ---------------------------------------------------------------- 엔드포인트
@app.get("/api/health")
def health():
    """프로세스 생존 확인. DB 가 있는지만 알려 주고 DB 를 열거나 만들지 않는다."""
    return {"status": "ok", "db_available": queries.get_db_path().is_file()}


@app.get("/api/programs")
def list_programs(
    tab: Tab = "deadline",
    q: Optional[str] = None,
    category: Optional[str] = None,
    date: Optional[date_type] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
    today=Depends(get_today),
):
    """활성 공고 목록. sort_programs 로 정렬한 뒤 필터와 페이지네이션을 적용한다.

    counts 는 q·category 필터를 적용한 뒤의 탭별 건수다(탭 선택·date 와는 무관). total 은 선택한 탭과 date 필터 후 건수.
    date 는 end_date 가 그 날짜인 공고만(만료 공고는 sort_programs 가 이미 뺐고, 마감일 없는 공고는 어떤 날짜에도 걸리지 않는다).
    """
    pairs = [(r, d) for r, d in sort_programs(queries.active_rows(conn), today) if _matches(r, q, category)]
    selected = pairs if tab == "all" else [p for p in pairs if p[1]["group"] in TAB_GROUPS[tab]]
    if date is not None:
        selected = [p for p in selected if deadline_on(p[0], p[1], date)]
    page = selected[offset: offset + limit]
    events = queries.events_by_source(queries.recent_events(conn, today, RECENT_DAYS))   # 쿼리 한 번(N+1 아님)
    items = [_item(r, d, badges(r["first_seen_at"], events.get(r["source_id"], []), today, RECENT_DAYS)) for r, d in page]
    return {"items": items, "total": len(selected), "counts": _tab_counts(pairs)}


def _parse_month(month):
    """'YYYY-MM' → (year, month). 형식이 틀리거나 연도가 2000~2100 밖이거나 월이 1~12 밖이면 422."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", month)
    if not m or not (2000 <= int(m[1]) <= 2100) or not (1 <= int(m[2]) <= 12):
        raise HTTPException(status_code=422, detail="month 는 YYYY-MM 형식이어야 하고 연도는 2000~2100 이다")
    return int(m[1]), int(m[2])


@app.get("/api/calendar")
def calendar(
    month: str = Query(..., description="YYYY-MM"),
    q: Optional[str] = None,
    category: Optional[str] = None,
    conn=Depends(get_conn),
    today=Depends(get_today),
):
    """월별 마감 달력. 그 달에 end_date 가 있는 모집중·모집예정 공고의 날짜별 건수(희소 형식: count >= 1 인 날짜만, 오름차순).

    /api/programs?date= 와 같은 판정(deadline_on)과 같은 q·category 매칭을 쓴다.
    """
    year, mon = _parse_month(month)
    counts = Counter()
    for r, d in sort_programs(queries.active_rows(conn), today):
        if _matches(r, q, category) and deadline_on(r, d):
            end = end_date_of(r)
            if (end.year, end.month) == (year, mon):
                counts[end] += 1
    return {"month": f"{year:04d}-{mon:02d}", "today": today.isoformat(),
            "days": [{"date": day.isoformat(), "count": n} for day, n in sorted(counts.items())]}


@app.get("/api/programs/{source_id}")
def get_program(source_id: str, conn=Depends(get_conn), today=Depends(get_today)):
    """공고 상세 + 전체 변경 이력(최신순). 비활성 행도 200 으로 돌려주되 is_active=false 이고 D-Day 는 없다."""
    row = queries.get_program(conn, source_id)
    if row is None:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없다")
    history = queries.program_history(conn, source_id)
    is_active = row["is_active"] == 1
    if is_active:
        display = compute_display(row, today)
        badge_list = badges(row["first_seen_at"], history, today, RECENT_DAYS)
    else:
        display = {"display_status": "비활성", "group": "inactive", "d_day": None, "d_day_label": None,
                   "source_status": row["source_status"]}
        badge_list = []
    item = _item(row, display, badge_list)
    item.update(summary=row["summary"], target=row["target"], schedule_text=row["schedule_text"],
                is_active=is_active, history=[_history_item(e) for e in history])
    return item


@app.get("/api/changes")
def list_changes(
    days: int = Query(7, ge=1, le=90),
    type: Optional[ChangeType] = None,
    conn=Depends(get_conn),
    today=Depends(get_today),
):
    """최근 days 일의 변경 목록(시각 내림차순). program_changes 이벤트와 파생 NEW(활성 행의 first_seen_at)를 합친다.

    counts 는 type 필터와 무관한 종류별 건수다.
    """
    items = [
        {"id": e["id"], "type": e["change_type"], "source_id": e["source_id"], "title": e["title"],
         "detected_at": e["detected_at"], "old_value": e["old_value"], "new_value": e["new_value"], "reason": e["reason"]}
        for e in queries.recent_events(conn, today, days) if queries.within_days(e["detected_at"], today, days)
    ]
    items += [
        {"id": None, "type": "new", "source_id": r["source_id"], "title": r["title"], "detected_at": r["first_seen_at"],
         "old_value": None, "new_value": None, "reason": None}
        for r in queries.active_rows(conn) if is_new(r["first_seen_at"], today=today, window_days=days)
    ]
    counts = dict(Counter(i["type"] for i in items))
    if type:
        items = [i for i in items if i["type"] == type]
    items.sort(key=lambda i: (queries.aware(i["detected_at"]), i["id"] or 0), reverse=True)
    return {"days": days, "total": len(items), "counts": counts, "items": items}


@app.get("/api/meta")
def meta(conn=Depends(get_conn), today=Depends(get_today)):
    rows = queries.active_rows(conn)
    pairs = sort_programs(rows, today)
    tab_counts = _tab_counts(pairs)
    tab_counts["all"] = len(pairs)
    events = [e for e in queries.recent_events(conn, today, RECENT_DAYS)
              if queries.within_days(e["detected_at"], today, RECENT_DAYS)]
    return {
        "today": today.isoformat(),
        "active_count": len(rows),
        "expired_active_count": len(rows) - len(pairs),      # 활성이지만 마감이 지나 목록에서 빠지는 행
        "tab_counts": tab_counts,
        "last_collected_at": queries.last_collected_at(conn),
        "window_days": RECENT_DAYS,
        "events_7d": dict(Counter(e["change_type"] for e in events)),
        "new_7d": sum(1 for r in rows if is_new(r["first_seen_at"], today=today, window_days=RECENT_DAYS)),
        "baseline_date": BASELINE_DATE.isoformat(),
    }
