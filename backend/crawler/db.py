"""SQLite 스키마 생성, upsert. 날짜·시각은 isoformat() 문자열로 저장한다."""
import sqlite3
from pathlib import Path

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
    updated_at    DATETIME
);

CREATE TABLE IF NOT EXISTS program_changes (
    id          INTEGER PRIMARY KEY,
    program_id  INTEGER NOT NULL REFERENCES programs(id),
    change_type TEXT,
    old_value   TEXT,
    new_value   TEXT,
    detected_at DATETIME
);
"""

# row 에서 None 이면 기존 값을 덮어쓰지 않는 컬럼
_KEEP_IF_NONE = (
    "title", "category", "organization", "target", "summary", "period_text",
    "schedule_text", "apply_url", "source_status", "source_url",
)
# 한 묶음으로 갱신하는 컬럼. period_type 이 None(상세 미수신)이면 셋 다 유지하고,
# 값이 있으면 start/end 가 None 이어도 덮어쓴다(dated → always 로 바뀐 공고에 옛 end_date 가 남지 않도록).
_PERIOD_UNIT = ("period_type", "start_date", "end_date")


def init_db(path):
    """DB 를 열고 스키마를 만든다. 연결을 반환한다(path 에 ':memory:' 가능)."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_program(conn, row, now):
    """source_id 기준 upsert. 신규면 True, 기존 행 갱신이면 False 를 반환한다. commit 은 호출자가 한다.

    - 신규: first_seen_at 기록. 기존: 값 갱신(상세 필드가 None 이면 기존 값 유지).
    - last_seen_at, updated_at 은 항상 now 로 갱신하고, 본 공고이므로 is_active=1.
    """
    ts = now.isoformat()
    existing = conn.execute(
        "SELECT id FROM programs WHERE source_id = ?", (row["source_id"],)
    ).fetchone()

    if existing is None:
        cols = ["source_id", *_KEEP_IF_NONE, *_PERIOD_UNIT]
        values = [row.get(c) for c in cols]
        conn.execute(
            f"INSERT INTO programs ({', '.join(cols)}, is_active, first_seen_at, last_seen_at, updated_at) "
            f"VALUES ({', '.join('?' * len(cols))}, 1, ?, ?, ?)",
            [*values, ts, ts, ts],
        )
        return True

    sets, values = [], []
    for c in _KEEP_IF_NONE:
        if row.get(c) is not None:
            sets.append(f"{c} = ?")
            values.append(row[c])
    if row.get("period_type") is not None:
        for c in _PERIOD_UNIT:
            sets.append(f"{c} = ?")
            values.append(row.get(c))
    sets += ["is_active = 1", "last_seen_at = ?", "updated_at = ?"]
    values += [ts, ts, row["source_id"]]
    conn.execute(f"UPDATE programs SET {', '.join(sets)} WHERE source_id = ?", values)
    return False


def deactivate_unseen(conn, seen_ids):
    """seen_ids 에 없는 공고는 is_active=0, 있는 공고는 is_active=1. 새로 비활성이 된 행 수를 반환한다.

    전체 수집이 완료됐을 때만 호출할 것(호출 규칙은 crawl.py). 삭제는 하지 않는다.
    seen_ids 가 비어 있으면 전부 비활성이 되므로 ValueError.
    """
    seen_ids = {str(i) for i in seen_ids}
    if not seen_ids:
        raise ValueError("seen_ids 가 비어 있어 전체를 비활성화할 수 없다")

    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _seen (source_id TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM _seen")
    conn.executemany("INSERT INTO _seen (source_id) VALUES (?)", [(i,) for i in seen_ids])
    try:
        cur = conn.execute(
            "UPDATE programs SET is_active = 0 "
            "WHERE is_active != 0 AND source_id NOT IN (SELECT source_id FROM _seen)"
        )
        deactivated = cur.rowcount
        conn.execute(
            "UPDATE programs SET is_active = 1 "
            "WHERE is_active != 1 AND source_id IN (SELECT source_id FROM _seen)"
        )
    finally:
        conn.execute("DROP TABLE _seen")
    return deactivated
