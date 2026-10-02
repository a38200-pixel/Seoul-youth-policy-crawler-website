"""SQLite 스키마 생성, upsert. 날짜·시각은 isoformat() 문자열로 저장한다."""
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .normalizer import KST, classify_period, today_kst

# 최초 적재 기준일. 이 날짜에 처음 본 행은 최초 적재분이라 NEW 가 아니다(기준일은 이 한 곳에서만 정의한다).
BASELINE_DATE = date(2026, 10, 1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS programs (
    id            INTEGER PRIMARY KEY,
    source_id     TEXT NOT NULL UNIQUE,
    title         TEXT,
    category      TEXT,
    organization  TEXT,
    target        TEXT,
    summary       TEXT,
    period_text   TEXT,
    period_type   TEXT,
    schedule_text TEXT,
    start_date    DATE,
    end_date      DATE,
    source_status TEXT,
    source_url    TEXT,
    apply_url     TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    first_seen_at DATETIME,
    last_seen_at  DATETIME,
    updated_at    DATETIME,
    detail_fetched_at DATETIME
);

CREATE TABLE IF NOT EXISTS program_changes (
    id          INTEGER PRIMARY KEY,
    source_id   TEXT NOT NULL,
    change_type TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    reason      TEXT,
    detected_at DATETIME NOT NULL
);
"""

# 변경 이벤트 종류
CHANGE_EXTENDED = "extended"
CHANGE_SHORTENED = "shortened"
CHANGE_PERIOD_CHANGED = "period_changed"
CHANGE_STATUS_CHANGED = "status_changed"
CHANGE_DEACTIVATED = "deactivated"
CHANGE_REACTIVATED = "reactivated"
# deactivated 의 reason
REASON_EXPIRED = "expired"
REASON_EARLY = "early"

# row 에서 None 이면 기존 값을 덮어쓰지 않는 컬럼
_KEEP_IF_NONE = (
    "title", "category", "organization", "target", "summary", "period_text",
    "schedule_text", "apply_url", "source_status", "source_url",
)
# 한 묶음으로 갱신하는 컬럼. period_type 이 None(상세 미수신)이면 셋 다 유지하고,
# 값이 있으면 start/end 가 None 이어도 덮어쓴다(dated → always 로 바뀐 공고에 옛 end_date 가 남지 않도록).
_PERIOD_UNIT = ("period_type", "start_date", "end_date")


def _migrate(conn):
    """기존 DB 에 없는 컬럼을 ALTER TABLE 로 추가한다. 기존 행의 값은 그대로(새 컬럼은 NULL)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(programs)")}
    if "detail_fetched_at" not in cols:
        # NULL = 상세를 받은 시각을 모른다 → 다음 실행에서 상세를 다시 받는다(백필하지 않음)
        conn.execute("ALTER TABLE programs ADD COLUMN detail_fetched_at DATETIME")


def _migrate_changes(conn):
    """옛 program_changes(program_id 기반, reason 없음)를 새 스키마(source_id, reason)로 바꾼다.

    - 이미 새 스키마면 아무것도 하지 않는다.
    - 비어 있으면 DROP 후 재생성한다.
    - 행이 있으면 새 테이블로 옮긴다: program_id 는 programs 에서 source_id 를 찾아 채우고(찾지 못하면 'id:<program_id>'),
      reason 은 NULL 로 둔다. 원본 테이블은 복사가 끝난 뒤에만 지운다.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(program_changes)")}
    if {"source_id", "reason"} <= cols:
        return
    n = conn.execute("SELECT COUNT(*) FROM program_changes").fetchone()[0]
    if n == 0:
        conn.execute("DROP TABLE program_changes")
        conn.execute("""
            CREATE TABLE program_changes (
                id          INTEGER PRIMARY KEY,
                source_id   TEXT NOT NULL,
                change_type TEXT NOT NULL,
                old_value   TEXT,
                new_value   TEXT,
                reason      TEXT,
                detected_at DATETIME NOT NULL
            )""")
        return
    conn.execute("ALTER TABLE program_changes RENAME TO program_changes_old")
    conn.execute("""
        CREATE TABLE program_changes (
            id          INTEGER PRIMARY KEY,
            source_id   TEXT NOT NULL,
            change_type TEXT NOT NULL,
            old_value   TEXT,
            new_value   TEXT,
            reason      TEXT,
            detected_at DATETIME NOT NULL
        )""")
    conn.execute("""
        INSERT INTO program_changes (id, source_id, change_type, old_value, new_value, reason, detected_at)
        SELECT o.id, COALESCE(p.source_id, 'id:' || o.program_id), COALESCE(o.change_type, 'unknown'),
               o.old_value, o.new_value, NULL, COALESCE(o.detected_at, '')
        FROM program_changes_old o LEFT JOIN programs p ON p.id = o.program_id""")
    conn.execute("DROP TABLE program_changes_old")


def init_db(path):
    """DB 를 열고 스키마를 만든다(기존 DB 는 컬럼 추가·테이블 변환). 연결을 반환한다(path 에 ':memory:' 가능)."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    _migrate_changes(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_program_changes_source ON program_changes (source_id, detected_at)")
    conn.commit()
    return conn


def _record_change(conn, source_id, change_type, old_value, new_value, ts, reason=None):
    conn.execute(
        "INSERT INTO program_changes (source_id, change_type, old_value, new_value, reason, detected_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (source_id, change_type, None if old_value is None else str(old_value),
         None if new_value is None else str(new_value), reason, ts))


def _period_json(period_type, start_date, end_date):
    return json.dumps({"period_type": period_type, "start_date": start_date, "end_date": end_date},
                      ensure_ascii=False)


def _detect_upsert_changes(conn, existing, row, has_detail, ts):
    """기존 행(existing)과 새 값(row)을 비교해 변경 이벤트를 기록한다. upsert 와 같은 트랜잭션(호출자가 commit)."""
    sid = row["source_id"]

    # status_changed: 목록의 모집상태가 바뀜 (둘 다 값이 있을 때만)
    old_status, new_status = existing["source_status"], row.get("source_status")
    if old_status is not None and new_status is not None and old_status != new_status:
        _record_change(conn, sid, CHANGE_STATUS_CHANGED, old_status, new_status, ts)

    # reactivated: 비활성이던 공고가 다시 보임
    if existing["is_active"] == 0:
        _record_change(conn, sid, CHANGE_REACTIVATED, "0", "1", ts)

    # period 계열은 이번에 상세를 받았고(has_detail) 이전에도 상세 기준값이 있을 때만 비교한다.
    # (이전 period_type 이 NULL 이면 처음 받는 것이라 변경이 아니다. 상세 수신 실패는 has_detail 이 False 라서 제외된다.)
    if has_detail and existing["period_type"] is not None:
        old_end, new_end = existing["end_date"], row.get("end_date")
        # extended / shortened: dated/end_only 의 end_date 가 이전 값보다 늦어지거나(extended) 이르러짐(shortened).
        # 이전·새 end_date 가 모두 있을 때만 비교한다(open → dated 처럼 이전 마감일이 없던 경우는 period_changed 몫).
        if old_end and new_end and new_end > old_end:
            _record_change(conn, sid, CHANGE_EXTENDED, old_end, new_end, ts)
        elif old_end and new_end and new_end < old_end:
            _record_change(conn, sid, CHANGE_SHORTENED, old_end, new_end, ts)
        # period_changed: start_date 또는 period_type 이 바뀜. end_date 만 바뀐 경우는 여기서 기록하지 않는다
        # (늦어졌든 이르러졌든 extended/shortened 하나만 남아 중복이 없다)
        new_start = row.get("start_date")
        if existing["period_type"] != row["period_type"] or existing["start_date"] != new_start:
            _record_change(
                conn, sid, CHANGE_PERIOD_CHANGED,
                _period_json(existing["period_type"], existing["start_date"], existing["end_date"]),
                _period_json(row["period_type"], new_start, new_end), ts)


def upsert_program(conn, row, now):
    """source_id 기준 upsert. 신규면 True, 기존 행 갱신이면 False 를 반환한다. commit 은 호출자가 한다.

    - 신규: first_seen_at 기록(NEW 는 이벤트 행으로 만들지 않는다). 기존: 값 갱신(상세 필드가 None 이면 기존 값 유지).
    - last_seen_at, updated_at 은 항상 now 로 갱신하고, 본 공고이므로 is_active=1.
    - detail_fetched_at 은 **상세를 받은 행(period_type 이 있는 row)일 때만** now 로 갱신한다. 목록만 본 upsert 는 건드리지 않는다.
    - 기존 행이면 갱신 전 값과 비교해 status_changed / reactivated / extended / period_changed 이벤트를
      program_changes 에 기록한다(같은 트랜잭션, 같은 값이면 기록하지 않는다).
    """
    ts = now.isoformat()
    has_detail = row.get("period_type") is not None
    existing = conn.execute(
        "SELECT id, source_status, period_type, start_date, end_date, is_active FROM programs WHERE source_id = ?",
        (row["source_id"],)
    ).fetchone()

    if existing is None:
        cols = ["source_id", *_KEEP_IF_NONE, *_PERIOD_UNIT]
        values = [row.get(c) for c in cols]
        conn.execute(
            f"INSERT INTO programs ({', '.join(cols)}, is_active, first_seen_at, last_seen_at, updated_at, "
            f"detail_fetched_at) VALUES ({', '.join('?' * len(cols))}, 1, ?, ?, ?, ?)",
            [*values, ts, ts, ts, ts if has_detail else None],
        )
        return True

    sets, values = [], []
    for c in _KEEP_IF_NONE:
        if row.get(c) is not None:
            sets.append(f"{c} = ?")
            values.append(row[c])
    if has_detail:
        for c in _PERIOD_UNIT:
            sets.append(f"{c} = ?")
            values.append(row.get(c))
        sets.append("detail_fetched_at = ?")
        values.append(ts)
    sets += ["is_active = 1", "last_seen_at = ?", "updated_at = ?"]
    values += [ts, ts, row["source_id"]]
    conn.execute(f"UPDATE programs SET {', '.join(sets)} WHERE source_id = ?", values)
    _detect_upsert_changes(conn, existing, row, has_detail, ts)
    return False


def _to_seoul_date(value):
    """isoformat 문자열·datetime·date 를 서울 기준 date 로. 해석할 수 없거나 비어 있으면 None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        return value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(KST)
    return dt.date()


to_seoul_date = _to_seoul_date   # 다른 모듈(crawl.py)에서 쓰는 공개 이름


def is_new(first_seen_at, today=None, window_days=7):
    """NEW 판정(순수 함수, 날짜 부분만 비교한다 — 시각은 보지 않는다).

    - first_seen_at 의 날짜가 BASELINE_DATE 보다 **뒤**(>)여야 한다. 기준일에 처음 본 행은 NEW 가 아니다.
    - today(생략하면 오늘의 서울 날짜)와의 날짜 차이가 window_days 이내(<=)여야 한다. 정확히 window_days 일 차이는 True, +1일은 False.
    first_seen_at 이 None/빈 문자열/해석 불가면 False.
    """
    first = _to_seoul_date(first_seen_at)
    if first is None or first <= BASELINE_DATE:
        return False
    today = today_kst() if today is None else _to_seoul_date(today)
    return (today - first).days <= window_days


def count_rows(conn):
    return conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]


def count_active(conn):
    return conn.execute("SELECT COUNT(*) FROM programs WHERE is_active = 1").fetchone()[0]


def detail_received_today(conn, source_id, today):
    """상세를 마지막으로 받은 시각(detail_fetched_at)의 날짜(Asia/Seoul)가 today(date)와 같은지.

    last_seen_at 은 쓰지 않는다(목록만 본 upsert 도 갱신하므로 어제 받은 상세를 오늘 받은 것으로 오인하게 된다).
    detail_fetched_at 이 NULL(받은 적 없음 / 마이그레이션 직후)이면 False.
    """
    r = conn.execute("SELECT detail_fetched_at FROM programs WHERE source_id = ?", (source_id,)).fetchone()
    if r is None or not r["detail_fetched_at"]:
        return False
    fetched = datetime.fromisoformat(r["detail_fetched_at"])
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=KST)
    return fetched.astimezone(KST).date() == today


def fetch_all(conn):
    return conn.execute(
        "SELECT source_id, title, category, period_type, period_text, target, organization, schedule_text "
        "FROM programs"
    ).fetchall()


def reclassify_periods(conn, now):
    """저장된 period_text 로 period_type/start_date/end_date 를 다시 계산해 바뀐 행만 갱신한다.

    period_text 가 NULL 인 행(상세 미수신)은 건드리지 않는다. 사이트 접속은 필요 없다. commit 은 호출자가 한다.
    분류 규칙을 바꾼 데 따른 재계산이므로 **변경 이벤트(program_changes)는 만들지 않는다.**
    반환: [(source_id, (old_type, old_start, old_end), (new_type, new_start, new_end)), ...]
    """
    ts = now.isoformat()
    changed = []
    rows = conn.execute(
        "SELECT source_id, period_text, period_type, start_date, end_date "
        "FROM programs WHERE period_text IS NOT NULL ORDER BY id"
    ).fetchall()
    for r in rows:
        period_type, start, end = classify_period(r["period_text"])
        new = (period_type, start.isoformat() if start else None, end.isoformat() if end else None)
        old = (r["period_type"], r["start_date"], r["end_date"])
        if new != old:
            conn.execute(
                "UPDATE programs SET period_type = ?, start_date = ?, end_date = ?, updated_at = ? "
                "WHERE source_id = ?", (*new, ts, r["source_id"]))
            changed.append((r["source_id"], old, new))
    return changed


def deactivate_unseen(conn, seen_ids, now=None):
    """seen_ids 에 없는 공고는 is_active=0, 있는 공고는 is_active=1. 새로 비활성이 된 행 수를 반환한다.

    전체 수집이 완료됐을 때만 호출할 것(호출 규칙은 crawl.py). 삭제는 하지 않는다.
    seen_ids 가 비어 있으면 전부 비활성이 되므로 ValueError.

    상태가 실제로 바뀐 행마다 이벤트를 기록한다(같은 트랜잭션, commit 은 호출자). 이미 비활성인 행은 다시 기록하지 않는다(멱등).
    - deactivated: is_active 1 → 0. reason 은 end_date 가 있고 end_date < 오늘(now 의 서울 날짜)이면 expired,
      그 외(마감일 전·당일, 마감일 없음, 상시 포함)는 early.
    - reactivated: is_active 0 → 1.
    now 를 생략하면 현재 서울 시각을 쓴다(테스트·재현을 위해 주입할 수 있다).
    """
    seen_ids = {str(i) for i in seen_ids}
    if not seen_ids:
        raise ValueError("seen_ids 가 비어 있어 전체를 비활성화할 수 없다")
    if now is None:
        now = datetime.now(KST)
    ts = now.isoformat()
    today = (now.astimezone(KST) if now.tzinfo else now).date().isoformat()

    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _seen (source_id TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM _seen")
    conn.executemany("INSERT INTO _seen (source_id) VALUES (?)", [(i,) for i in seen_ids])
    try:
        to_off = conn.execute(
            "SELECT source_id, end_date FROM programs "
            "WHERE is_active != 0 AND source_id NOT IN (SELECT source_id FROM _seen) ORDER BY id"
        ).fetchall()
        to_on = conn.execute(
            "SELECT source_id FROM programs "
            "WHERE is_active != 1 AND source_id IN (SELECT source_id FROM _seen) ORDER BY id"
        ).fetchall()
        cur = conn.execute(
            "UPDATE programs SET is_active = 0 "
            "WHERE is_active != 0 AND source_id NOT IN (SELECT source_id FROM _seen)"
        )
        deactivated = cur.rowcount
        conn.execute(
            "UPDATE programs SET is_active = 1 "
            "WHERE is_active != 1 AND source_id IN (SELECT source_id FROM _seen)"
        )
        for r in to_off:
            reason = REASON_EXPIRED if r["end_date"] and r["end_date"] < today else REASON_EARLY
            _record_change(conn, r["source_id"], CHANGE_DEACTIVATED, "1", "0", ts, reason)
        for r in to_on:
            _record_change(conn, r["source_id"], CHANGE_REACTIVATED, "0", "1", ts)
    finally:
        conn.execute("DROP TABLE _seen")
    return deactivated
