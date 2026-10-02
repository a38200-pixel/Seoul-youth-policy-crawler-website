"""표시 규칙(순수 함수). DB·네트워크 접근이 없고, today 는 인자로 주입한다(기본값은 Asia/Seoul 오늘).

- compute_display(row, today): 한 행의 표시 상태·D-Day·그룹·정렬 키를 계산한다.
- sort_programs(rows, today): 표시 순서대로 정렬한다(expired 는 제외).
- badges(first_seen_at, events, today, window_days): NEW 와 최근 변경 이벤트 배지를 만든다.

날짜만 쓴다: 시각(예: "18 : 00")은 무시하고, 진행일정(schedule_text)은 쓰지 않는다.
"""
import json
from datetime import date, datetime

from backend.crawler.db import is_new, to_seoul_date
from backend.crawler.normalizer import today_kst

# group 이름과 정렬 순서(앞이 먼저). expired 는 정렬 대상에서 제외한다.
GROUP_RECRUITING = "recruiting"     # 모집중(D-Day)
GROUP_UPCOMING = "upcoming"         # 모집예정(시작 D-n)
GROUP_OPEN = "open"                 # 마감일 미정
GROUP_ALWAYS = "always"             # 상시(분야 있음)
GROUP_ALWAYS_ETC = "always_etc"     # 상시-기타(분야 없음)
GROUP_UNKNOWN = "unknown"           # 확인 필요
GROUP_EXPIRED = "expired"           # 마감 지남
GROUP_ORDER = (GROUP_RECRUITING, GROUP_UPCOMING, GROUP_OPEN, GROUP_ALWAYS, GROUP_ALWAYS_ETC, GROUP_UNKNOWN)
HIDDEN_BY_DEFAULT = frozenset({GROUP_EXPIRED, GROUP_ALWAYS_ETC})

_FAR_FUTURE = "9999-12-31"


def _get(row, key):
    """dict 와 sqlite3.Row 를 모두 받는다. 없는 키는 None."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _date(value):
    """date / datetime / 'YYYY-MM-DD…' 문자열 → date(서울 기준). 시각 부분은 버린다. 해석 불가면 None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return to_seoul_date(value)
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return to_seoul_date(datetime.fromisoformat(text))   # offset 이 있으면 서울 날짜로 환산(is_new 와 같은 기준)
    except ValueError:
        try:
            return date.fromisoformat(text[:10])             # "2026-10-06 18 : 00" 처럼 시각 형식이 제각각이면 날짜 부분만
        except ValueError:
            return None


def _today(today):
    return today_kst() if today is None else _date(today)


def _sid_key(source_id):
    """source_id 정렬 키: 숫자는 숫자 순서(9 < 10), 그 외는 문자열 순서 뒤에."""
    s = str(source_id or "")
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


def _result(source_status, display_status, d_day, d_day_label, group, sort_key):
    return {"display_status": display_status, "d_day": d_day, "d_day_label": d_day_label,
            "group": group, "sort_key": sort_key, "source_status": source_status}


def _upcoming(source_status, start, today, sid_key):
    n = (start - today).days
    return _result(source_status, "모집예정", n, f"시작 D-{n}", GROUP_UPCOMING, (1, start.isoformat(), sid_key))


def compute_display(row, today=None):
    """행(period_type, start_date, end_date, source_status, category, source_id)의 표시 값을 계산한다.

    반환: {display_status, d_day, d_day_label, group, sort_key, source_status}
    - dated/end_only: end < today → expired / start > today → 모집예정('시작 D-n', 사이트 상태가 모집중이어도 날짜 우선) /
      그 외 모집중(D-Day, D-n).
    - open: 시작일이 미래면 모집예정 표시, 아니면 '마감일 미정'(D-Day 없음).
    - always: '상시'. category 가 있으면 group='always', 비어 있으면 'always_etc'(기본 숨김).
    - unknown(및 상세 미수신·해석 불가): '확인 필요'.
    """
    today = _today(today)
    status = _get(row, "source_status")
    ptype = _get(row, "period_type")
    sid_key = _sid_key(_get(row, "source_id"))
    start, end = _date(_get(row, "start_date")), _date(_get(row, "end_date"))

    if ptype in ("dated", "end_only") and end is not None:
        if end < today:
            return _result(status, "마감", None, None, GROUP_EXPIRED, None)
        if start is not None and start > today:
            return _upcoming(status, start, today, sid_key)
        n = (end - today).days
        return _result(status, "모집중", n, "D-Day" if n == 0 else f"D-{n}", GROUP_RECRUITING,
                       (0, n, end.isoformat(), sid_key))

    if ptype == "open":
        if start is not None and start > today:
            return _upcoming(status, start, today, sid_key)
        return _result(status, "마감일 미정", None, None, GROUP_OPEN,
                       (2, start.isoformat() if start else _FAR_FUTURE, sid_key))

    if ptype == "always":
        category = (_get(row, "category") or "").strip()
        if category:
            return _result(status, "상시", None, None, GROUP_ALWAYS, (3, category, sid_key))
        return _result(status, "상시", None, None, GROUP_ALWAYS_ETC, (4, sid_key))

    return _result(status, "확인 필요", None, None, GROUP_UNKNOWN, (5, sid_key))


def visible_by_default(display):
    """기본 목록에 보이는지(expired 와 always_etc 는 숨김)."""
    return display["group"] not in HIDDEN_BY_DEFAULT


def sort_programs(rows, today=None):
    """표시 순서대로 정렬한 [(row, display), …]. expired 는 정렬 대상에서 제외한다.

    순서: 모집중(d_day 오름차순, 동률은 end_date, source_id) → 모집예정(start_date 오름차순) → 마감일 미정 → 상시 → 상시-기타 → 확인 필요.
    """
    today = _today(today)
    pairs = [(r, compute_display(r, today)) for r in rows]
    pairs = [p for p in pairs if p[1]["group"] != GROUP_EXPIRED]
    pairs.sort(key=lambda p: p[1]["sort_key"])
    return pairs


# ---------------------------------------------------------------- 배지
BADGE_LABELS = {
    "new": "NEW", "extended": "연장", "shortened": "단축", "period_changed": "기간 변경",
    "status_changed": "상태 변경", "reactivated": "재등록",
}
BADGE_ORDER = tuple(BADGE_LABELS)   # NEW → 연장 → 단축 → 기간 변경 → 상태 변경 → 재등록
# deactivated 는 활성 행의 배지로 쓰지 않는다(BADGE_LABELS 에 없다)


def _period_text(value):
    """period_changed 의 JSON 값 → 'open 2026-09-20 ~ -' 처럼 읽기 쉬운 문자열."""
    try:
        d = json.loads(value)
        return f"{d['period_type']} {d.get('start_date') or '-'} ~ {d.get('end_date') or '-'}"
    except (TypeError, ValueError, KeyError):
        return str(value)


def _detail(change_type, old, new):
    if change_type == "reactivated":
        return None
    if change_type == "period_changed":
        return f"{_period_text(old)} → {_period_text(new)}"
    return f"{old} → {new}"


def _event_dt(event):
    return datetime.fromisoformat(_get(event, "detected_at"))


def badges(first_seen_at, events, today=None, window_days=7):
    """NEW + 최근 window_days 이내 변경 이벤트로 배지를 만든다. 반환: [{type, label, detail, detected_at}, …] (BADGE_ORDER 순).

    - NEW: db.is_new(first_seen_at, today, window_days) (기준일 당일 첫 적재분은 NEW 가 아니다).
    - 연장/단축/기간 변경/상태 변경: 종류별로 window 이내 가장 최근 1건만, detail 에 'old → new' 문자열을 담는다.
    - 재등록(reactivated): window 이내 가장 최근 1건, detail 없음. deactivated 는 배지로 쓰지 않는다.
    window 판정은 is_new 와 같다: 날짜(서울) 차이가 window_days 이내(<=)면 포함(정확히 7일 차이는 포함, 8일 차이는 제외).
    """
    today = _today(today)
    result = []
    if is_new(first_seen_at, today=today, window_days=window_days):
        result.append({"type": "new", "label": BADGE_LABELS["new"], "detail": None, "detected_at": first_seen_at})

    latest = {}
    for e in events or []:
        ctype = _get(e, "change_type")
        if ctype not in BADGE_LABELS or ctype == "new":
            continue
        d = _date(_get(e, "detected_at"))
        if d is None or (today - d).days > window_days:
            continue
        key = (_event_dt(e), _get(e, "id") or 0)          # 가장 최근, 같은 시각이면 id 가 큰 것
        if ctype not in latest or key > latest[ctype][0]:
            latest[ctype] = (key, e)
    for ctype in BADGE_ORDER:
        if ctype in latest:
            e = latest[ctype][1]
            result.append({"type": ctype, "label": BADGE_LABELS[ctype],
                           "detail": _detail(ctype, _get(e, "old_value"), _get(e, "new_value")),
                           "detected_at": _get(e, "detected_at")})
    return result
