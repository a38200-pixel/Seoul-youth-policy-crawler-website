"""변경 감지(program_changes 이벤트) 테스트. 임시 DB(:memory:, tmp_path)만 쓰고 실제 DB 에는 접근하지 않는다."""
import json
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.crawler.crawl import run_crawl
from backend.crawler.db import (BASELINE_DATE, deactivate_unseen, init_db, is_new, reclassify_periods,
                                upsert_program)
from backend.crawler.record import make_row

SAMPLES = Path(__file__).resolve().parent.parent / "backend" / "crawler" / "samples"
DETAIL_SAMPLE = (SAMPLES / "detail_sample.html").read_text(encoding="utf-8")  # 신청기간 2026-09-29 ~ 2026-10-09
KST = timezone(timedelta(hours=9))
D1 = datetime(2026, 10, 1, 9, 0, tzinfo=KST)
D2 = datetime(2026, 10, 2, 9, 0, tzinfo=KST)   # '오늘'
D3 = datetime(2026, 10, 3, 9, 0, tzinfo=KST)
EMPTY = "<html><body><div class='category-feed'></div></body></html>"


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def item(sid="1", status="모집중"):
    return {"source_id": sid, "title": f"공고{sid}", "category": "금융", "status": status}


def up(conn, sid, period_text, now, status="모집중"):
    """period_text 가 None 이면 목록만 받은 upsert(detail=None)."""
    detail = None if period_text is None else {"period_text": period_text}
    return upsert_program(conn, make_row(item(sid, status), detail), now)


def events(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM program_changes ORDER BY id")]


def kinds(conn):
    return [e["change_type"] for e in events(conn)]


def active(conn, sid):
    return conn.execute("SELECT is_active FROM programs WHERE source_id = ?", (sid,)).fetchone()[0]


# ---------------------------------------------------------------- 스키마
def test_new_schema_columns(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(program_changes)")]
    assert cols == ["id", "source_id", "change_type", "old_value", "new_value", "reason", "detected_at"]
    assert events(conn) == []


# ---------------------------------------------------------------- NEW 는 이벤트가 아니다
def test_new_program_creates_no_event(conn):
    assert up(conn, "1", "2026-10-01 ~ 2026-10-08", D1) is True
    assert events(conn) == []


# ---------------------------------------------------------------- extended
def test_extended_for_dated(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D1)
    up(conn, "1", "2026-10-01 ~ 2026-10-15", D2)
    assert events(conn) == [{
        "id": 1, "source_id": "1", "change_type": "extended",
        "old_value": "2026-10-08", "new_value": "2026-10-15", "reason": None, "detected_at": D2.isoformat()}]


def test_extended_for_end_only(conn):
    up(conn, "1", "~ 2026-10-08 00 : 00", D1)
    up(conn, "1", "~ 2026-10-10 00 : 00", D2)
    e = events(conn)
    assert [(x["change_type"], x["old_value"], x["new_value"]) for x in e] == [("extended", "2026-10-08", "2026-10-10")]


def test_end_date_only_extension_is_not_duplicated_as_period_changed(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D1)
    up(conn, "1", "2026-10-01 ~ 2026-10-31", D2)
    assert kinds(conn) == ["extended"]          # period_changed 가 함께 생기면 안 된다


# ---------------------------------------------------------------- shortened (extended 의 대칭)
def test_shortened_for_dated(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-15", D1)
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D2)
    assert events(conn) == [{
        "id": 1, "source_id": "1", "change_type": "shortened",
        "old_value": "2026-10-15", "new_value": "2026-10-08", "reason": None, "detected_at": D2.isoformat()}]


def test_shortened_for_end_only(conn):
    up(conn, "1", "~ 2026-10-10 00 : 00", D1)
    up(conn, "1", "~ 2026-10-06 00 : 00", D2)
    e = events(conn)
    assert [(x["change_type"], x["old_value"], x["new_value"]) for x in e] == [("shortened", "2026-10-10", "2026-10-06")]


def test_shortened_is_not_duplicated_as_period_changed(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-15", D1)
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D2)
    assert kinds(conn) == ["shortened"]          # period_changed 가 함께 생기면 안 된다


def test_shortened_and_start_change_record_both_without_duplicates(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-15", D1)
    up(conn, "1", "2026-10-03 ~ 2026-10-08", D2)
    assert kinds(conn) == ["shortened", "period_changed"]


def test_shortened_is_idempotent(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-15", D1)
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D2)
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D3)                 # 같은 값 재실행
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D3 + timedelta(hours=1))
    assert kinds(conn) == ["shortened"]


def test_extended_and_shortened_are_symmetric(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D1)
    up(conn, "1", "2026-10-01 ~ 2026-10-15", D2)                 # 연장
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D3)                 # 원래대로 단축
    e = events(conn)
    assert [(x["change_type"], x["old_value"], x["new_value"], x["reason"]) for x in e] == [
        ("extended", "2026-10-08", "2026-10-15", None),
        ("shortened", "2026-10-15", "2026-10-08", None)]         # old/new 가 정확히 뒤바뀐다


def test_no_shortened_when_previous_end_date_is_missing(conn):
    up(conn, "1", "2026-09-20 ~ 00 : 00 [ 선착순 마감 ]", D1)      # open: 이전 마감일 없음
    up(conn, "1", "2026-09-20 ~ 2026-10-20", D2)
    assert kinds(conn) == ["period_changed"]                     # shortened/extended 는 없다


def test_dated_becoming_open_is_not_shortened(conn):
    up(conn, "1", "2026-09-20 ~ 2026-10-20", D1)
    up(conn, "1", "2026-09-20 ~ 00 : 00 [ 선착순 마감 ]", D2)      # 새 마감일이 없다
    assert kinds(conn) == ["period_changed"]


# ---------------------------------------------------------------- period_changed
def test_period_changed_when_start_date_changes(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D1)
    up(conn, "1", "2026-10-02 ~ 2026-10-08", D2)
    (e,) = events(conn)
    assert e["change_type"] == "period_changed"
    assert json.loads(e["old_value"]) == {"period_type": "dated", "start_date": "2026-10-01", "end_date": "2026-10-08"}
    assert json.loads(e["new_value"]) == {"period_type": "dated", "start_date": "2026-10-02", "end_date": "2026-10-08"}


def test_period_changed_when_open_becomes_dated(conn):
    up(conn, "1", "2026-09-20 ~ 00 : 00 [ 선착순 마감 ]", D1)      # open: 마감일 미정
    up(conn, "1", "2026-09-20 ~ 2026-10-20", D2)                  # 마감일 확정
    (e,) = events(conn)                                          # extended 는 이전 end 가 없어 생기지 않는다
    assert e["change_type"] == "period_changed"
    assert json.loads(e["old_value"]) == {"period_type": "open", "start_date": "2026-09-20", "end_date": None}
    assert json.loads(e["new_value"]) == {"period_type": "dated", "start_date": "2026-09-20", "end_date": "2026-10-20"}


def test_period_changed_when_end_only_gets_a_start(conn):
    up(conn, "1", "~ 2026-10-08 00 : 00", D1)
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D2)
    assert kinds(conn) == ["period_changed"]                     # end_date 는 그대로


def test_extended_and_start_change_record_both_without_duplicates(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D1)
    up(conn, "1", "2026-10-03 ~ 2026-10-20", D2)
    assert kinds(conn) == ["extended", "period_changed"]


# ---------------------------------------------------------------- status_changed
def test_status_changed(conn):
    up(conn, "1", None, D1, status="모집예정")
    up(conn, "1", None, D2, status="모집중")
    (e,) = events(conn)
    assert (e["change_type"], e["old_value"], e["new_value"], e["reason"]) == ("status_changed", "모집예정", "모집중", None)


def test_missing_status_is_not_a_change(conn):
    up(conn, "1", None, D1, status="모집중")
    upsert_program(conn, make_row({"source_id": "1", "title": "공고1", "category": "금융", "status": None}, None), D2)
    assert events(conn) == []


# ---------------------------------------------------------------- deactivated: expired / early
@pytest.mark.parametrize("period_text, reason", [
    ("2026-09-20 ~ 2026-10-01", "expired"),                  # end_date 가 어제
    ("2026-09-20 ~ 2026-10-02", "early"),                    # 오늘(오늘 마감은 아직 지난 것이 아님)
    ("2026-09-20 ~ 2026-10-03", "early"),                    # 내일
    ("상시", "early"),                                        # end_date 없음(상시)
    ("2026-09-20 ~ 00 : 00 [ 선착순 마감 ]", "early"),          # end_date 없음(마감일 미정)
])
def test_deactivated_reason(conn, period_text, reason):
    up(conn, "A", period_text, D1)
    up(conn, "Z", "상시", D1)
    assert deactivate_unseen(conn, ["Z"], D2) == 1               # D2 = 2026-10-02 가 '오늘'
    (e,) = events(conn)
    assert (e["source_id"], e["change_type"], e["old_value"], e["new_value"], e["reason"], e["detected_at"]) == \
        ("A", "deactivated", "1", "0", reason, D2.isoformat())


def test_deactivated_uses_seoul_date_for_today(conn):
    up(conn, "A", "2026-09-20 ~ 2026-10-01", D1)
    up(conn, "Z", "상시", D1)
    utc_now = datetime(2026, 10, 1, 16, 30, tzinfo=timezone.utc)   # = 2026-10-02 01:30 KST → 오늘은 10-02
    deactivate_unseen(conn, ["Z"], utc_now)
    assert events(conn)[0]["reason"] == "expired"


def test_deactivate_mixed_rows_each_get_their_own_reason(conn):
    for sid, text in (("A", "2026-09-20 ~ 2026-10-01"), ("B", "~ 2026-09-30 00 : 00"),
                      ("C", "2026-09-20 ~ 2026-10-09"), ("D", "상시"), ("Z", "상시")):
        up(conn, sid, text, D1)
    deactivate_unseen(conn, ["Z"], D2)
    assert {e["source_id"]: e["reason"] for e in events(conn)} == \
        {"A": "expired", "B": "expired", "C": "early", "D": "early"}


def test_deactivated_is_idempotent(conn):
    up(conn, "A", "2026-09-20 ~ 2026-10-01", D1)
    up(conn, "Z", "상시", D1)
    deactivate_unseen(conn, ["Z"], D2)
    deactivate_unseen(conn, ["Z"], D3)                           # 이미 비활성 → 다시 기록하지 않는다
    assert kinds(conn) == ["deactivated"]


# ---------------------------------------------------------------- reactivated
def test_reactivated_by_upsert_and_rerun_is_idempotent(conn):
    up(conn, "A", "2026-09-20 ~ 2026-10-09", D1)
    up(conn, "Z", "상시", D1)
    deactivate_unseen(conn, ["Z"], D2)
    assert active(conn, "A") == 0
    up(conn, "A", "2026-09-20 ~ 2026-10-09", D3)                 # 다시 보임
    assert kinds(conn) == ["deactivated", "reactivated"]
    e = events(conn)[1]
    assert (e["old_value"], e["new_value"], e["reason"], e["detected_at"]) == ("0", "1", None, D3.isoformat())
    up(conn, "A", "2026-09-20 ~ 2026-10-09", D3 + timedelta(hours=1))   # 같은 값 재실행
    assert kinds(conn) == ["deactivated", "reactivated"]


def test_reactivated_by_deactivate_unseen(conn):
    up(conn, "A", "상시", D1)
    up(conn, "Z", "상시", D1)
    deactivate_unseen(conn, ["Z"], D2)
    deactivate_unseen(conn, ["A", "Z"], D3)                      # A 가 seen 에 다시 들어옴
    assert kinds(conn) == ["deactivated", "reactivated"]
    deactivate_unseen(conn, ["A", "Z"], D3)
    assert kinds(conn) == ["deactivated", "reactivated"]


# ---------------------------------------------------------------- 멱등 / 무이벤트 원칙
def test_rerun_with_same_values_creates_no_events(conn):
    for now in (D1, D2, D3):
        up(conn, "1", "2026-10-01 ~ 2026-10-08", now, status="모집중")
        up(conn, "2", "상시", now, status="상시")
        up(conn, "3", None, now, status="모집예정")
    assert events(conn) == []


def test_reclassify_creates_no_events(conn):
    conn.execute("INSERT INTO programs (source_id, period_text, period_type, is_active, source_status) "
                 "VALUES ('a', '2026-09-20 ~ 00 : 00 [ 선착순 마감 ]', 'unknown', 1, '모집중')")
    conn.execute("INSERT INTO programs (source_id, period_text, period_type, start_date, end_date, is_active, source_status) "
                 "VALUES ('b', '상시', 'dated', '2026-01-01', '2026-12-31', 1, '상시')")
    changed = reclassify_periods(conn, D2)
    assert [c[0] for c in changed] == ["a", "b"]                 # 실제로 값은 바뀌었지만
    assert events(conn) == []                                    # 이벤트는 없다
    up(conn, "a", "2026-09-20 ~ 00 : 00 [ 선착순 마감 ]", D3)       # 재분류된 값과 같은 상세가 오면 이것도 변경이 아니다
    assert events(conn) == []


def test_reclassify_records_no_shortened(conn):
    # 저장된 end_date 가 재분류 결과보다 늦은(낡은) 행: 재분류로 end_date 가 이르러져도 이벤트는 없다
    conn.execute("INSERT INTO programs (source_id, period_text, period_type, start_date, end_date, is_active, source_status) "
                 "VALUES ('a', '2026-09-20 ~ 2026-10-01', 'dated', '2026-09-20', '2026-10-20', 1, '모집중')")
    changed = reclassify_periods(conn, D2)
    assert changed and changed[0][2][2] == "2026-10-01"
    assert events(conn) == []


def test_detail_none_is_not_a_change(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D1)
    up(conn, "1", None, D2)                                      # 상세 수신 실패/미수신: 목록 값만
    assert events(conn) == []
    row = conn.execute("SELECT period_type, start_date, end_date FROM programs WHERE source_id='1'").fetchone()
    assert tuple(row) == ("dated", "2026-10-01", "2026-10-08")   # 기존 값도 유지된다


def test_list_only_run_can_only_produce_status_events(conn):
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D1, status="모집중")
    up(conn, "1", None, D2, status="모집예정")
    assert kinds(conn) == ["status_changed"]                     # period 계열은 만들어지지 않는다


def test_first_detail_receipt_is_not_a_change(conn):
    up(conn, "1", None, D1)                                      # 목록만 받아 period_type 이 NULL
    up(conn, "1", "2026-10-01 ~ 2026-10-08", D2)                 # 처음 받는 상세: 비교할 이전 값이 없다
    assert events(conn) == []


# ---------------------------------------------------------------- run_crawl 수준 (부분 실행·중단·UTC/KST)
def list_html(ids, status="모집중"):
    items = "".join(
        f'<div class="feed-item"><a class="item-overlay" onclick="goView(\'{i}\');"></a>'
        f'<div class="content"><span class="cate">금융</span><div class="name">공고{i}</div>'
        f'<span class="state">{status}</span></div></div>' for i in ids)
    return f'<html><body><div class="category-feed">{items}</div></body></html>'


class Fake:
    def __init__(self, pages, detail_html=DETAIL_SAMPLE, fail=()):
        self.pages, self.detail_html, self.fail = pages, detail_html, set(fail)

    def fetch_list(self, page):
        return self.pages.get(page, EMPTY)

    def fetch_detail(self, source_id):
        return None if source_id in self.fail else self.detail_html


@pytest.fixture
def db(tmp_path):
    return tmp_path / "youth.db"


def seed_old(db_path):
    c = init_db(db_path)
    up(c, "old0", None, D1)                                      # 활성, 목록만 받은 행(end_date 없음)
    c.commit()
    c.close()


def db_events(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute("SELECT * FROM program_changes ORDER BY id")]
    finally:
        c.close()


def test_full_run_records_deactivated_with_kst_timestamp(db, caplog):
    seed_old(db)
    with caplog.at_level(logging.INFO):
        stats = run_crawl(Fake({1: list_html(["1", "2"])}), db, D2)
    assert stats.deactivated == 1
    (e,) = db_events(db)
    assert (e["source_id"], e["change_type"], e["reason"], e["detected_at"]) == \
        ("old0", "deactivated", "early", D2.isoformat())
    assert e["detected_at"].endswith("+09:00")                   # Asia/Seoul
    assert "변경 이벤트(이번 실행): deactivated 1건" in caplog.text


@pytest.mark.parametrize("kwargs", [{"max_pages": 1}, {"detail_limit": 1}], ids=["max-pages", "detail-limit"])
def test_partial_runs_never_create_deactivated(db, kwargs):
    seed_old(db)
    stats = run_crawl(Fake({1: list_html(["1", "2"])}), db, D2, **kwargs)
    assert stats.deactivated is None
    assert db_events(db) == []


def test_aborted_run_never_creates_deactivated(db):
    seed_old(db)
    ids = [str(i) for i in range(1, 16)]
    stats = run_crawl(Fake({1: list_html(ids)}, fail=ids), db, D2)
    assert stats.abort_reason and stats.deactivated is None
    assert db_events(db) == []


def test_run_level_rerun_is_idempotent_and_status_change_is_detected(db, caplog):
    run_crawl(Fake({1: list_html(["1"], "모집예정")}), db, D2)
    with caplog.at_level(logging.INFO):
        run_crawl(Fake({1: list_html(["1"], "모집예정")}), db, D2 + timedelta(hours=1))   # 같은 값 재실행
    assert db_events(db) == []
    assert "변경 이벤트(이번 실행): 없음" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.INFO):
        run_crawl(Fake({1: list_html(["1"], "모집중")}), db, D3)                          # 상태가 바뀜
    (e,) = db_events(db)
    assert (e["change_type"], e["old_value"], e["new_value"], e["detected_at"]) == \
        ("status_changed", "모집예정", "모집중", D3.isoformat())
    assert "변경 이벤트(이번 실행): status_changed 1건" in caplog.text


def test_run_level_extension_is_detected_when_detail_is_refetched_next_day(db):
    run_crawl(Fake({1: list_html(["1"])}), db, D2)                                      # 신청기간 2026-09-29 ~ 2026-10-09
    extended_html = DETAIL_SAMPLE.replace("2026-10-09", "2026-10-20")
    run_crawl(Fake({1: list_html(["1"])}, detail_html=extended_html), db, D3)           # 다음 날 상세를 다시 받음
    (e,) = db_events(db)                                                                # period_changed 중복 없음
    assert (e["change_type"], e["old_value"], e["new_value"]) == ("extended", "2026-10-09", "2026-10-20")


def test_run_level_shortening_is_detected_when_detail_is_refetched_next_day(db):
    run_crawl(Fake({1: list_html(["1"])}), db, D2)                                      # 신청기간 2026-09-29 ~ 2026-10-09
    shortened_html = DETAIL_SAMPLE.replace("2026-10-09", "2026-10-05")
    run_crawl(Fake({1: list_html(["1"])}, detail_html=shortened_html), db, D3)
    (e,) = db_events(db)                                                                # period_changed 중복 없음
    assert (e["change_type"], e["old_value"], e["new_value"]) == ("shortened", "2026-10-09", "2026-10-05")


def test_runs_without_detail_record_no_shortened(db):
    run_crawl(Fake({1: list_html(["1", "2"])}), db, D2)                                 # 두 행 모두 end 2026-10-09
    shortened_html = DETAIL_SAMPLE.replace("2026-10-09", "2026-10-05")
    for kwargs in ({"no_detail": True}, {"detail_limit": 0}):                           # 상세를 받지 않는 실행
        run_crawl(Fake({1: list_html(["1", "2"])}, detail_html=shortened_html), db, D3, **kwargs)
    assert db_events(db) == []
    c = sqlite3.connect(db)
    assert {r[0] for r in c.execute("SELECT end_date FROM programs")} == {"2026-10-09"}   # 값도 그대로
    c.close()


def test_partial_run_records_shortened_only_for_rows_whose_detail_was_received(db):
    # 부분 실행(--detail-limit)이라도 상세를 실제로 받은 행은 실제 변경이므로 기록한다(extended 와 같은 규칙).
    # 상세를 받지 못한 행(한도 초과)에는 기록이 없다.
    run_crawl(Fake({1: list_html(["1", "2"])}), db, D2)
    shortened_html = DETAIL_SAMPLE.replace("2026-10-09", "2026-10-05")
    run_crawl(Fake({1: list_html(["1", "2"])}, detail_html=shortened_html), db, D3, detail_limit=1)
    (e,) = db_events(db)
    assert (e["source_id"], e["change_type"]) == ("1", "shortened")


def test_run_level_refetch_with_same_detail_creates_no_events(db):
    run_crawl(Fake({1: list_html(["1", "2"])}), db, D2)
    run_crawl(Fake({1: list_html(["1", "2"])}), db, D3)                                 # 다음 날 같은 상세
    assert db_events(db) == []


def test_run_level_reclassify_at_start_creates_no_events(db):
    c = init_db(db)
    c.execute("INSERT INTO programs (source_id, period_text, period_type, is_active, source_status) "
              "VALUES ('x', '~ 00 : 00 [ 선착순 마감 ]', 'unknown', 1, '모집중')")
    c.commit()
    c.close()
    run_crawl(Fake({1: list_html(["1"])}), db, D2, max_pages=1)                         # 시작 때 자동 재분류가 돈다
    c = sqlite3.connect(db)
    assert c.execute("SELECT period_type FROM programs WHERE source_id='x'").fetchone()[0] == "open"
    c.close()
    assert db_events(db) == []


# ---------------------------------------------------------------- NEW 판정: is_new (순수 함수, 날짜 부분만 비교)
TODAY = date(2026, 10, 2)


def test_baseline_date_is_defined_once_in_db():
    assert BASELINE_DATE == date(2026, 10, 1)


@pytest.mark.parametrize("first_seen_at, expected", [
    ("2026-10-01T22:10:00+09:00", False),   # 기준일에 처음 본 행(최초 적재분)은 NEW 가 아니다
    ("2026-10-01T00:00:00+09:00", False),
    ("2026-10-01T23:59:59+09:00", False),   # 시각이 늦어도 날짜가 기준일이면 False
    ("2026-10-02T07:00:00+09:00", True),    # 기준일 다음 날
    ("2026-10-02T00:00:00+09:00", True),
    ("2026-10-02", True),                    # 날짜만 있는 값도 처리
    ("2026-09-30T10:00:00+09:00", False),   # 기준일 이전
    (None, False),
    ("", False),
    ("날짜 아님", False),
])
def test_is_new_baseline_rule(first_seen_at, expected):
    assert is_new(first_seen_at, today=TODAY) is expected


@pytest.mark.parametrize("today, expected", [
    (date(2026, 10, 2), True),     # 0일 차
    (date(2026, 10, 8), True),     # 6일 차
    (date(2026, 10, 9), True),     # 정확히 7일 차: window 이내
    (date(2026, 10, 10), False),   # 8일 차: window 초과
    (date(2026, 11, 1), False),
])
def test_is_new_window_boundary_default_7_days(today, expected):
    assert is_new("2026-10-02T07:00:00+09:00", today=today) is expected


def test_is_new_compares_dates_only_not_time_of_day():
    # 같은 날짜라면 시각이 달라도 결과가 같다(정확히 7일 차의 이른 시각·늦은 시각 모두 True, 8일 차는 모두 False)
    for first in ("2026-10-02T00:00:00+09:00", "2026-10-02T23:59:59+09:00"):
        assert is_new(first, today=date(2026, 10, 9)) is True
        assert is_new(first, today=date(2026, 10, 10)) is False


@pytest.mark.parametrize("window_days, today, expected", [
    (3, date(2026, 10, 5), True),     # 정확히 3일 차
    (3, date(2026, 10, 6), False),    # 4일 차
    (0, date(2026, 10, 2), True),     # 당일만
    (0, date(2026, 10, 3), False),
    (30, date(2026, 11, 1), True),    # 30일 차
    (30, date(2026, 11, 2), False),   # 31일 차
])
def test_is_new_custom_window(window_days, today, expected):
    assert is_new("2026-10-02T07:00:00+09:00", today=today, window_days=window_days) is expected


def test_is_new_converts_other_offsets_to_seoul_date():
    # 2026-10-01T16:30Z = 2026-10-02 01:30 KST → 기준일 다음 날이므로 NEW
    assert is_new("2026-10-01T16:30:00+00:00", today=TODAY) is True
    # 2026-10-01T14:59Z = 2026-10-01 23:59 KST → 기준일이므로 NEW 아님
    assert is_new("2026-10-01T14:59:00+00:00", today=TODAY) is False


def test_is_new_accepts_date_and_datetime_inputs():
    assert is_new(date(2026, 10, 2), today=TODAY) is True
    assert is_new(date(2026, 10, 1), today=TODAY) is False
    assert is_new(datetime(2026, 10, 2, 7, 0, tzinfo=KST), today=datetime(2026, 10, 9, 23, 0, tzinfo=KST)) is True


def test_is_new_defaults_today_to_seoul_today(monkeypatch):
    monkeypatch.setattr("backend.crawler.db.today_kst", lambda: date(2026, 10, 9))
    assert is_new("2026-10-02T07:00:00+09:00") is True                  # 7일 차
    monkeypatch.setattr("backend.crawler.db.today_kst", lambda: date(2026, 10, 10))
    assert is_new("2026-10-02T07:00:00+09:00") is False                 # 8일 차


def test_first_seen_at_written_by_upsert_follows_the_rule(conn):
    up(conn, "old", "상시", datetime(2026, 10, 1, 22, 10, tzinfo=KST))   # 기준일에 처음 본 행
    up(conn, "new", "상시", datetime(2026, 10, 2, 7, 0, tzinfo=KST))     # 기준일 다음 날 처음 본 행
    fs = {r["source_id"]: r["first_seen_at"] for r in conn.execute("SELECT source_id, first_seen_at FROM programs")}
    assert fs == {"old": "2026-10-01T22:10:00+09:00", "new": "2026-10-02T07:00:00+09:00"}
    assert [sid for sid, v in fs.items() if is_new(v, today=TODAY)] == ["new"]
    assert events(conn) == []                                                # NEW 는 이벤트 행이 아니다


# ---------------------------------------------------------------- 옛 program_changes 스키마 마이그레이션
OLD_CHANGES = """
DROP TABLE program_changes;
CREATE TABLE program_changes (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES programs(id),
    change_type TEXT, old_value TEXT, new_value TEXT, detected_at DATETIME
);
"""


def make_old_db(path, rows=()):
    c = init_db(path)                       # programs 등 현재 스키마를 만든 뒤 program_changes 만 옛 모양으로 되돌린다
    up(c, "74531", "상시", D1)              # programs.id = 1
    c.commit()
    c.executescript(OLD_CHANGES)
    for r in rows:
        c.execute("INSERT INTO program_changes (program_id, change_type, old_value, new_value, detected_at) "
                  "VALUES (?, ?, ?, ?, ?)", r)
    c.commit()
    c.close()


def columns(path):
    c = sqlite3.connect(path)
    try:
        return [r[1] for r in c.execute("PRAGMA table_info(program_changes)")]
    finally:
        c.close()


def test_migration_recreates_empty_old_table(tmp_path):
    path = tmp_path / "old.db"
    make_old_db(path)
    assert "program_id" in columns(path)
    init_db(path).close()
    assert columns(path) == ["id", "source_id", "change_type", "old_value", "new_value", "reason", "detected_at"]
    init_db(path).close()                                            # 멱등
    assert columns(path)[1] == "source_id"


def test_migration_copies_existing_rows_when_not_empty(tmp_path):
    path = tmp_path / "old.db"
    make_old_db(path, rows=[(1, "extended", "2026-10-01", "2026-10-08", "2026-10-01T09:00:00+09:00"),
                            (999, "status_changed", "a", "b", "2026-10-01T10:00:00+09:00")])   # 999: programs 에 없는 id
    init_db(path).close()
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    got = [dict(r) for r in c.execute("SELECT * FROM program_changes ORDER BY id")]
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    c.close()
    assert [(g["source_id"], g["change_type"], g["old_value"], g["new_value"], g["reason"]) for g in got] == \
        [("74531", "extended", "2026-10-01", "2026-10-08", None), ("id:999", "status_changed", "a", "b", None)]
    assert "program_changes_old" not in names                        # 복사가 끝난 뒤 원본은 지워진다


def test_migration_leaves_new_schema_untouched(tmp_path):
    path = tmp_path / "new.db"
    c = init_db(path)
    up(c, "1", "2026-10-01 ~ 2026-10-08", D1)
    up(c, "1", "2026-10-01 ~ 2026-10-15", D2)
    c.commit()
    c.close()
    c = init_db(path)                                                # 두 번째 열기: 새 스키마라 그대로
    assert kinds(c) == ["extended"]
    c.close()
