import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.crawler.db import (deactivate_unseen, detail_received_today, init_db, reclassify_periods,
                                upsert_program)
from backend.crawler.detail_parser import parse_detail
from backend.crawler.record import make_row

SAMPLES = Path(__file__).resolve().parent.parent / "backend" / "crawler" / "samples"
NOW = datetime(2026, 10, 1, 9, 0, 0)
LATER = NOW + timedelta(days=1)


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def item(source_id="1", status="모집중"):
    return {"source_id": source_id, "title": f"공고{source_id}", "category": "금융", "status": status}


def sample_row(name, source_id="100", status="모집중"):
    detail = parse_detail((SAMPLES / name).read_text(encoding="utf-8"))
    return make_row(item(source_id, status), detail)


def get(conn, source_id):
    return conn.execute("SELECT * FROM programs WHERE source_id = ?", (source_id,)).fetchone()


def count(conn):
    return conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]


def test_schema_has_both_tables_and_new_columns(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(programs)")}
    assert {"period_type", "schedule_text", "is_active", "first_seen_at"} <= cols
    assert conn.execute("SELECT COUNT(*) FROM program_changes").fetchone()[0] == 0


def test_insert_new(conn):
    assert upsert_program(conn, make_row(item("1"), None), NOW) is True
    r = get(conn, "1")
    assert count(conn) == 1
    assert r["is_active"] == 1
    assert r["first_seen_at"] == r["last_seen_at"] == r["updated_at"] == NOW.isoformat()


def test_rerun_keeps_row_count_and_updates_last_seen(conn):
    upsert_program(conn, make_row(item("1"), None), NOW)
    assert upsert_program(conn, make_row(item("1"), None), LATER) is False
    r = get(conn, "1")
    assert count(conn) == 1
    assert r["first_seen_at"] == NOW.isoformat()
    assert r["last_seen_at"] == LATER.isoformat()
    assert r["updated_at"] == LATER.isoformat()


def test_list_only_upsert_keeps_detail_fields(conn):
    upsert_program(conn, sample_row("detail_sample.html", "100"), NOW)
    before = dict(get(conn, "100"))
    assert before["organization"] and before["period_type"] == "dated"

    upsert_program(conn, make_row(item("100", "모집중"), None), LATER)  # 목록만 (detail=None)
    after = dict(get(conn, "100"))
    # 상세 전용 필드는 그대로 유지된다
    for key in ("organization", "target", "summary", "period_text",
                "period_type", "schedule_text", "start_date", "end_date", "apply_url"):
        assert after[key] == before[key], key
    assert after["last_seen_at"] == LATER.isoformat()
    # title/category 는 목록에서도 얻는 필드라 목록 값(None 아님)으로 갱신된다
    assert after["title"] == "공고100"


def test_none_title_category_keep_existing_and_values_update(conn):
    upsert_program(conn, make_row({"source_id": "7", "title": "원래 제목", "category": "금융", "status": "모집중"}, None), NOW)

    # 목록 값이 None 이면 기존 값 유지
    upsert_program(conn, make_row({"source_id": "7", "title": None, "category": None, "status": "모집중"}, None), LATER)
    r = get(conn, "7")
    assert (r["title"], r["category"]) == ("원래 제목", "금융")

    # 값이 있으면 갱신
    upsert_program(conn, make_row({"source_id": "7", "title": "바뀐 제목", "category": "주거", "status": "모집중"}, None), LATER)
    r = get(conn, "7")
    assert (r["title"], r["category"]) == ("바뀐 제목", "주거")


def test_dated_to_always_clears_old_end_date(conn):
    upsert_program(conn, sample_row("detail_sample.html", "100"), NOW)
    assert get(conn, "100")["end_date"] == "2026-10-09"
    upsert_program(conn, sample_row("detail_sample_always.html", "100"), LATER)
    r = get(conn, "100")
    assert r["period_type"] == "always"
    assert r["start_date"] is None and r["end_date"] is None


def test_detail_fetched_at_set_only_when_detail_received(conn):
    upsert_program(conn, make_row(item("9"), None), NOW)                       # 목록만
    assert get(conn, "9")["detail_fetched_at"] is None

    upsert_program(conn, sample_row("detail_sample.html", "9"), LATER)         # 상세 수신
    assert get(conn, "9")["detail_fetched_at"] == LATER.isoformat()

    much_later = LATER + timedelta(days=3)
    upsert_program(conn, make_row(item("9"), None), much_later)                # 다시 목록만
    r = get(conn, "9")
    assert r["detail_fetched_at"] == LATER.isoformat()                         # 안 바뀜
    assert r["last_seen_at"] == much_later.isoformat()                         # last_seen_at 만 갱신


def test_reclassify_does_not_touch_detail_fetched_at(conn):
    upsert_program(conn, make_row(item("9"), {"period_text": "~ 2026-10-08"}), NOW)
    conn.execute("UPDATE programs SET period_type = 'unknown', end_date = NULL WHERE source_id = '9'")
    reclassify_periods(conn, LATER)
    assert get(conn, "9")["detail_fetched_at"] == NOW.isoformat()


def test_detail_received_today_by_date_in_seoul(conn):
    kst = timezone(timedelta(hours=9))
    upsert_program(conn, make_row(item("9"), {"period_text": "상시"}), datetime(2026, 10, 1, 9, 0, tzinfo=kst))
    assert detail_received_today(conn, "9", date(2026, 10, 1)) is True
    assert detail_received_today(conn, "9", date(2026, 10, 2)) is False        # 어제 받음 → 오늘이 아님
    assert detail_received_today(conn, "nope", date(2026, 10, 1)) is False     # 없는 공고

    # UTC 로 저장돼 있어도 서울 날짜로 비교한다: 2026-10-01T16:30Z = 2026-10-02 01:30 KST
    conn.execute("UPDATE programs SET detail_fetched_at = '2026-10-01T16:30:00+00:00' WHERE source_id = '9'")
    assert detail_received_today(conn, "9", date(2026, 10, 2)) is True
    assert detail_received_today(conn, "9", date(2026, 10, 1)) is False
    # 시간대 없는 값은 서울 시각으로 본다
    conn.execute("UPDATE programs SET detail_fetched_at = '2026-10-01T23:30:00' WHERE source_id = '9'")
    assert detail_received_today(conn, "9", date(2026, 10, 1)) is True


def test_detail_received_today_false_when_never_received(conn):
    upsert_program(conn, make_row(item("9"), None), NOW)
    assert detail_received_today(conn, "9", NOW.date()) is False


def test_init_db_adds_column_to_existing_db_and_keeps_rows(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE programs (
            id INTEGER PRIMARY KEY, source_id TEXT NOT NULL UNIQUE, title TEXT, category TEXT, organization TEXT,
            target TEXT, summary TEXT, period_text TEXT, period_type TEXT, schedule_text TEXT, start_date DATE,
            end_date DATE, source_status TEXT, source_url TEXT, apply_url TEXT, is_active INTEGER NOT NULL DEFAULT 1,
            first_seen_at DATETIME, last_seen_at DATETIME, updated_at DATETIME);
        INSERT INTO programs (source_id, title, period_text, period_type, last_seen_at)
            VALUES ('74531', '기존 행', '~ 2026-10-08', 'end_only', '2026-10-01T17:01:54+09:00');
    """)
    old.commit()
    old.close()

    c = init_db(path)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(programs)")}
    assert "detail_fetched_at" in cols
    r = c.execute("SELECT * FROM programs WHERE source_id = '74531'").fetchone()
    assert (r["title"], r["period_type"], r["last_seen_at"]) == ("기존 행", "end_only", "2026-10-01T17:01:54+09:00")
    assert r["detail_fetched_at"] is None       # 백필하지 않음 → 다음 실행에서 상세를 다시 받는다
    c.close()

    init_db(path).close()                       # 두 번째 호출도 에러 없이 통과(멱등)


def test_dated_to_end_only_clears_start_date(conn):
    # 4-A 의 기간 묶음 규칙: period_type 이 있으면 start/end 를 한 묶음으로 덮어쓴다
    dated = make_row(item("5"), {"period_text": "2026-10-01 ~ 2026-10-08"})
    upsert_program(conn, dated, NOW)
    r = get(conn, "5")
    assert (r["period_type"], r["start_date"], r["end_date"]) == ("dated", "2026-10-01", "2026-10-08")

    end_only = make_row(item("5"), {"period_text": "~ 2026-10-08 00 : 00"})
    upsert_program(conn, end_only, LATER)
    r = get(conn, "5")
    assert (r["period_type"], r["start_date"], r["end_date"]) == ("end_only", None, "2026-10-08")


def test_endonly_sample_through_parse_and_make_row(conn):
    upsert_program(conn, sample_row("detail_sample_endonly.html", "74531"), NOW)
    r = get(conn, "74531")
    assert r["period_type"] == "end_only"
    assert r["period_text"] == "~ 2026-10-08 00 : 00"
    assert r["start_date"] is None and r["end_date"] == "2026-10-08"
    kinds = conn.execute(
        "SELECT typeof(start_date), typeof(end_date) FROM programs WHERE source_id='74531'").fetchone()
    assert tuple(kinds) == ("null", "text")


def put_raw(conn, source_id, period_text, period_type, start, end):
    conn.execute(
        "INSERT INTO programs (source_id, period_text, period_type, start_date, end_date, is_active, "
        "first_seen_at, last_seen_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
        (source_id, period_text, period_type, start, end, NOW.isoformat(), NOW.isoformat(), NOW.isoformat()))


def test_reclassify_updates_only_changed_rows(conn):
    put_raw(conn, "a", "~ 2026-10-08 00 : 00", "unknown", None, None)                 # → end_only
    put_raw(conn, "b", "2026-10-01 ~ 2026-10-08", "dated", "2026-10-01", "2026-10-08")  # 그대로
    put_raw(conn, "c", "상시", "dated", "2026-01-01", "2026-12-31")                      # → always, 날짜 비움
    put_raw(conn, "d", None, None, None, None)                                          # 상세 미수신: 건드리지 않음
    put_raw(conn, "e", None, "unknown", None, None)                                     # period_text NULL: 건드리지 않음

    changed = reclassify_periods(conn, LATER)

    assert [c[0] for c in changed] == ["a", "c"]
    assert changed[0][1:] == (("unknown", None, None), ("end_only", None, "2026-10-08"))
    assert changed[1][1:] == (("dated", "2026-01-01", "2026-12-31"), ("always", None, None))
    assert (get(conn, "a")["period_type"], get(conn, "a")["end_date"]) == ("end_only", "2026-10-08")
    assert (get(conn, "c")["start_date"], get(conn, "c")["end_date"]) == (None, None)
    assert get(conn, "a")["updated_at"] == LATER.isoformat()
    assert get(conn, "b")["updated_at"] == NOW.isoformat()      # 안 바뀐 행은 updated_at 도 그대로
    d, e = get(conn, "d"), get(conn, "e")
    assert (d["period_type"], e["period_type"]) == (None, "unknown")
    assert get(conn, "a")["last_seen_at"] == NOW.isoformat()    # last_seen_at 은 건드리지 않음


def test_reclassify_is_idempotent(conn):
    put_raw(conn, "a", "~ 2026-10-08", "unknown", None, None)
    assert len(reclassify_periods(conn, NOW)) == 1
    assert reclassify_periods(conn, NOW) == []


def test_deactivate_unseen(conn):
    for sid in ("1", "2", "3"):
        upsert_program(conn, make_row(item(sid), None), NOW)

    assert deactivate_unseen(conn, ["1", "3"]) == 1
    assert [get(conn, s)["is_active"] for s in ("1", "2", "3")] == [1, 0, 1]
    assert count(conn) == 3  # 삭제하지 않는다

    # 다시 보이면 되살아난다
    deactivate_unseen(conn, ["1", "2", "3"])
    assert get(conn, "2")["is_active"] == 1


def test_upsert_reactivates_seen_program(conn):
    upsert_program(conn, make_row(item("1"), None), NOW)
    deactivate_unseen(conn, ["999"])
    assert get(conn, "1")["is_active"] == 0
    upsert_program(conn, make_row(item("1"), None), LATER)
    assert get(conn, "1")["is_active"] == 1


def test_deactivate_unseen_rejects_empty(conn):
    upsert_program(conn, make_row(item("1"), None), NOW)
    with pytest.raises(ValueError):
        deactivate_unseen(conn, [])
    assert get(conn, "1")["is_active"] == 1


def test_always_sample_through_parse_and_make_row(conn):
    upsert_program(conn, sample_row("detail_sample_always.html", "200", "상시"), NOW)
    r = get(conn, "200")
    assert r["period_type"] == "always"
    assert r["period_text"] == "상시 [ 선착순 마감 ]"
    assert r["end_date"] is None and r["start_date"] is None
    assert r["schedule_text"] == "2026-11-07 00:00:00 14시 0분 ~ 15시 30분"
    kinds = conn.execute(
        "SELECT typeof(start_date), typeof(end_date), typeof(first_seen_at) FROM programs WHERE source_id='200'"
    ).fetchone()
    assert tuple(kinds) == ("null", "null", "text")


def test_dated_sample_through_parse_and_make_row(conn):
    upsert_program(conn, sample_row("detail_sample.html", "300"), NOW)
    r = get(conn, "300")
    assert r["period_type"] == "dated"
    assert r["start_date"] == "2026-09-29"
    assert r["end_date"] == "2026-10-09"
    kinds = conn.execute(
        "SELECT typeof(start_date), typeof(end_date), typeof(last_seen_at) FROM programs WHERE source_id='300'"
    ).fetchone()
    assert tuple(kinds) == ("text", "text", "text")
