from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.crawler.db import deactivate_unseen, init_db, upsert_program
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


def test_dated_to_always_clears_old_end_date(conn):
    upsert_program(conn, sample_row("detail_sample.html", "100"), NOW)
    assert get(conn, "100")["end_date"] == "2026-10-09"
    upsert_program(conn, sample_row("detail_sample_always.html", "100"), LATER)
    r = get(conn, "100")
    assert r["period_type"] == "always"
    assert r["start_date"] is None and r["end_date"] is None


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
