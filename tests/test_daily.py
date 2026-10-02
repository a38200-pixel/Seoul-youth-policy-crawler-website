"""--daily / --daily-plan 일일 수집 정책 테스트. 임시 DB 와 가짜 fetcher 만 쓴다(네트워크·실제 DB 없음)."""
import hashlib
import logging
import os
import sqlite3
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.crawler import crawl
from backend.crawler.crawl import (DAILY_ALWAYS_CAP, DAILY_ALWAYS_REFRESH_DAYS, DAILY_PLAN_COLUMNS,
                                   build_daily_plan, parse_args, plan_daily_targets, run_crawl, run_daily_plan)
from backend.crawler.db import init_db, upsert_program
from backend.crawler.record import make_row

SAMPLES = Path(__file__).resolve().parent.parent / "backend" / "crawler" / "samples"
DETAIL_SAMPLE = (SAMPLES / "detail_sample.html").read_text(encoding="utf-8")
KST = timezone(timedelta(hours=9))
RUN = datetime(2026, 10, 20, 9, 0, tzinfo=KST)      # '오늘' = 2026-10-20
TODAY = date(2026, 10, 20)
EMPTY = "<html><body><div class='category-feed'></div></body></html>"

# source_id 는 숫자여야 한다(목록 파서가 goView('숫자') 만 읽는다)
NEW, DATED, END_ONLY, OPEN, UNKNOWN, ALWAYS_RECENT, A8, A7, A6, GONE = (
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "99")


def ago(days):
    return RUN - timedelta(days=days)


def item(sid, status="모집중"):
    return {"source_id": sid, "title": f"공고{sid}", "category": "금융", "status": status}


def seed(conn, sid, period_text, fetched_at, status="모집중"):
    """상세를 fetched_at 에 받은 행을 만든다. period_text 가 None 이면 상세 없이 목록만 받은 행(detail_fetched_at NULL)."""
    detail = None if period_text is None else {"period_text": period_text}
    upsert_program(conn, make_row(item(sid, status), detail), fetched_at)


def rows_of(conn):
    return {r["source_id"]: r for r in conn.execute(f"SELECT {DAILY_PLAN_COLUMNS} FROM programs")}


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def seed_policy_rows(conn):
    seed(conn, NEW, None, ago(1))                                   # 상세를 받은 적 없음 → 신규
    seed(conn, DATED, "2026-10-25 ~ 2026-10-30", ago(1))
    seed(conn, END_ONLY, "~ 2026-10-25 00 : 00", ago(1))
    seed(conn, OPEN, "2026-10-01 ~ 00 : 00 [ 선착순 마감 ]", ago(1))
    seed(conn, UNKNOWN, "추후 공지", ago(1))
    seed(conn, ALWAYS_RECENT, "상시", ago(1), status="상시")


# ---------------------------------------------------------------- 대상 판정 (순수 함수 / 계획)
def test_policy_constants():
    assert DAILY_ALWAYS_REFRESH_DAYS == 7
    assert DAILY_ALWAYS_CAP == 200


def test_new_dated_open_unknown_end_only_are_targets_but_recent_always_is_not(conn):
    seed_policy_rows(conn)
    plan = build_daily_plan(rows_of(conn), TODAY)
    assert plan["reasons"] == {NEW: "new", DATED: "regular", END_ONLY: "regular", OPEN: "regular", UNKNOWN: "regular"}
    assert ALWAYS_RECENT not in plan["reasons"]
    assert dict(plan["counts"]) == {"new": 1, "regular": 4}
    assert dict(plan["regular_by_type"]) == {"dated": 1, "end_only": 1, "open": 1, "unknown": 1}


@pytest.mark.parametrize("days, is_target", [(8, True), (7, True), (6, False), (0, False)])
def test_always_row_becomes_target_after_7_days(conn, days, is_target):
    seed(conn, A8, "상시", ago(days), status="상시")
    reasons = build_daily_plan(rows_of(conn), TODAY)["reasons"]
    assert (reasons == {A8: "always"}) if is_target else (reasons == {})


def test_always_cap_is_200_and_oldest_first(conn):
    ids = [str(1000 + i) for i in range(250)]
    base = RUN - timedelta(days=30)
    for i in reversed(range(250)):                                  # 일부러 나이 순서와 반대로 넣는다
        seed(conn, ids[i], "상시", base + timedelta(minutes=i), status="상시")   # i 가 작을수록 오래됨
    plan = build_daily_plan(rows_of(conn), TODAY)
    assert plan["always_candidates"] == 250                         # 후보는 250 건, 상한 적용 후 200 건
    assert plan["always_selected"] == 200
    assert set(plan["reasons"]) == set(ids[:200])                   # 가장 오래된 200 건
    assert not set(ids[200:]) & set(plan["reasons"])


def test_inactive_rows_are_excluded_from_the_plan(conn):
    seed(conn, DATED, "2026-10-25 ~ 2026-10-30", ago(1))
    seed(conn, NEW, None, ago(1))
    seed(conn, A8, "상시", ago(30), status="상시")
    conn.execute("UPDATE programs SET is_active = 0")               # 전부 비활성
    plan = build_daily_plan(rows_of(conn), TODAY)
    assert plan["active"] == 0 and plan["reasons"] == {}


def test_targets_are_deduplicated_by_priority(conn):
    # detail_fetched_at 이 NULL 이면서 period_type 이 dated 인 행: 신규(a)와 상시 외(b)에 모두 해당 → 한 번만, 신규로
    conn.execute("INSERT INTO programs (source_id, period_type, is_active, source_status) VALUES ('21', 'dated', 1, '모집중')")
    # 상태가 바뀐 오래된 always 행: 상태 변경(c)와 상시 갱신(d)에 모두 해당 → 한 번만, 상태 변경으로
    seed(conn, A8, "상시", ago(30), status="상시")
    reasons, candidates = plan_daily_targets(["21", A8], rows_of(conn), TODAY, {"21": "모집중", A8: "모집중"})
    assert reasons == {"21": "new", A8: "status"}
    assert candidates == 0                                          # (d) 후보에서도 빠진다(이미 (c)로 대상)


def test_status_change_makes_any_period_type_a_target(conn):
    seed(conn, ALWAYS_RECENT, "상시", ago(1), status="상시")        # 최근에 받은 always: 원래는 대상 아님
    seed(conn, A6, "상시", ago(1), status="상시")
    reasons, _ = plan_daily_targets([ALWAYS_RECENT, A6], rows_of(conn), TODAY, {ALWAYS_RECENT: "모집중", A6: "상시"})
    assert reasons == {ALWAYS_RECENT: "status"}                     # 상태가 바뀐 행만


def test_plan_without_list_statuses_never_reports_status_changes(conn):
    seed(conn, ALWAYS_RECENT, "상시", ago(1), status="상시")
    reasons, _ = plan_daily_targets([ALWAYS_RECENT], rows_of(conn), TODAY, None)
    assert reasons == {}


# ---------------------------------------------------------------- run_crawl(daily=True)
def list_html(pairs):
    items = "".join(
        f'<div class="feed-item"><a class="item-overlay" onclick="goView(\'{i}\');"></a>'
        f'<div class="content"><span class="cate">금융</span><div class="name">공고{i}</div>'
        f'<span class="state">{st}</span></div></div>' for i, st in pairs)
    return f'<html><body><div class="category-feed">{items}</div></body></html>'


class Fake:
    def __init__(self, pages, fail=()):
        self.pages, self.fail = pages, set(fail)
        self.detail_calls = []

    def fetch_list(self, page):
        return self.pages.get(page, EMPTY)

    def fetch_detail(self, source_id):
        self.detail_calls.append(source_id)
        return None if source_id in self.fail else DETAIL_SAMPLE


@pytest.fixture
def db(tmp_path):
    return tmp_path / "youth.db"


def prepare(db_path, fn):
    c = init_db(db_path)
    fn(c)
    c.commit()
    c.close()


def rows_in(db_path, sql="SELECT * FROM programs"):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute(sql)]
    finally:
        c.close()


def test_daily_fetches_only_policy_targets(db, caplog):
    def setup(c):
        seed(c, DATED, "2026-10-25 ~ 2026-10-30", ago(1))
        seed(c, ALWAYS_RECENT, "상시", ago(1), status="상시")
        seed(c, A8, "상시", ago(8), status="상시")
        seed(c, GONE, "2026-10-25 ~ 2026-10-30", ago(1))
        c.execute("UPDATE programs SET is_active = 0 WHERE source_id = ?", (GONE,))      # 비활성(목록에도 없음)
    prepare(db, setup)
    fetcher = Fake({1: list_html([(NEW, "모집중"), (DATED, "모집중"), (ALWAYS_RECENT, "상시"), (A8, "상시")])})
    with caplog.at_level(logging.INFO):
        stats = run_crawl(fetcher, db, RUN, daily=True)
    assert sorted(fetcher.detail_calls) == sorted([NEW, DATED, A8])           # 신규 + 상시 외 + 오래된 상시
    assert GONE not in fetcher.detail_calls and ALWAYS_RECENT not in fetcher.detail_calls
    assert dict(stats.daily_counts) == {"new": 1, "regular": 1, "always": 1}
    assert stats.detail_skipped_policy == 1 and stats.detail_ok == 3
    assert stats.partial_run is False                                          # --daily 단독은 부분 실행이 아니다
    # 실행 요약: 대상 구분별 건수, 실제 요청 수, 이벤트 종류별 건수
    assert ("일일 정책(--daily): 신규 1건 / 상시 외 매일 1건 / 상태 변경 0건 / 상시 갱신 1건 → 대상 합계 3건"
            in caplog.text)
    assert "정책상 제외 1건 | 실제 상세 요청 3건" in caplog.text
    assert "변경 이벤트(이번 실행):" in caplog.text


def test_daily_skips_rows_whose_detail_was_received_today(db):
    prepare(db, lambda c: seed(c, DATED, "2026-10-25 ~ 2026-10-30", RUN))       # 오늘 받음
    fetcher = Fake({1: list_html([(DATED, "모집중")])})
    stats = run_crawl(fetcher, db, RUN, daily=True)
    assert fetcher.detail_calls == []                                          # 정책 대상이지만 오늘 받아서 건너뜀
    assert stats.daily_counts["regular"] == 1 and stats.detail_skipped_today == 1


def test_daily_status_change_in_list_makes_an_always_row_a_target(db):
    def setup(c):
        seed(c, ALWAYS_RECENT, "상시", ago(1), status="상시")
        seed(c, A6, "상시", ago(1), status="상시")
    prepare(db, setup)
    fetcher = Fake({1: list_html([(ALWAYS_RECENT, "모집중"), (A6, "상시")])})   # 이번 목록에서 앞의 행만 상태가 바뀜
    stats = run_crawl(fetcher, db, RUN, daily=True)
    assert fetcher.detail_calls == [ALWAYS_RECENT]
    assert dict(stats.daily_counts) == {"status": 1}


def test_daily_always_cap_limits_requests_per_run(db):
    ids = [str(1000 + i) for i in range(250)]
    base = RUN - timedelta(days=30)

    def setup(c):
        for i, sid in enumerate(ids):
            seed(c, sid, "상시", base + timedelta(minutes=i), status="상시")
    prepare(db, setup)
    fetcher = Fake({1: list_html([(sid, "상시") for sid in ids])})
    stats = run_crawl(fetcher, db, RUN, daily=True)
    assert len(fetcher.detail_calls) == 200 and set(fetcher.detail_calls) == set(ids[:200])
    assert stats.daily_always_candidates == 250 and stats.daily_counts["always"] == 200


def test_daily_runs_are_a_complete_collection_and_call_deactivate_unseen(db):
    prepare(db, lambda c: seed(c, GONE, None, ago(1)))                          # 활성이지만 이번 목록에 없는 행
    stats = run_crawl(Fake({1: list_html([(NEW, "모집중"), (DATED, "모집중")])}), db, RUN, daily=True)
    assert stats.deactivated == 1                                              # 호출됐고 GONE 이 비활성이 됨
    assert rows_in(db, f"SELECT is_active FROM programs WHERE source_id = '{GONE}'")[0]["is_active"] == 0
    kinds = [r["change_type"] for r in rows_in(db, "SELECT * FROM program_changes")]
    assert kinds == ["deactivated"]


def test_daily_keeps_the_50_percent_check(db, caplog):
    def setup(c):
        for i in range(20):
            seed(c, str(500 + i), None, ago(1))                                # 직전 활성 20 건, 이번 목록에는 2 건만
    prepare(db, setup)
    with caplog.at_level(logging.WARNING):
        stats = run_crawl(Fake({1: list_html([(NEW, "모집중"), (DATED, "모집중")])}), db, RUN, daily=True)
    assert stats.deactivated is None and "50% 미만" in caplog.text
    assert all(r["is_active"] == 1 for r in rows_in(db, "SELECT is_active FROM programs WHERE source_id >= '500'"))


@pytest.mark.parametrize("kwargs", [{"detail_limit": 1}, {"max_pages": 1}], ids=["detail-limit", "max-pages"])
def test_daily_with_detail_limit_or_max_pages_is_a_partial_run(db, kwargs):
    prepare(db, lambda c: seed(c, GONE, None, ago(1)))
    stats = run_crawl(Fake({1: list_html([(NEW, "모집중"), (DATED, "모집중")])}), db, RUN, daily=True, **kwargs)
    assert stats.partial_run is True and stats.deactivated is None             # deactivate_unseen 호출 안 함
    assert rows_in(db, f"SELECT is_active FROM programs WHERE source_id = '{GONE}'")[0]["is_active"] == 1
    assert rows_in(db, "SELECT * FROM program_changes") == []


def test_daily_detail_limit_still_caps_requests(db):
    fetcher = Fake({1: list_html([(str(30 + i), "모집중") for i in range(5)])})
    stats = run_crawl(fetcher, db, RUN, daily=True, detail_limit=2)
    assert len(fetcher.detail_calls) == 2 and stats.detail_skipped_option == 3


def test_daily_aborted_run_does_not_deactivate(db):
    prepare(db, lambda c: seed(c, GONE, None, ago(1)))
    ids = [str(40 + i) for i in range(12)]                                      # 12 건 모두 신규 → 모두 대상 → 모두 실패
    stats = run_crawl(Fake({1: list_html([(i, "모집중") for i in ids])}, fail=ids), db, RUN, daily=True)
    assert stats.abort_reason and stats.deactivated is None
    assert rows_in(db, f"SELECT is_active FROM programs WHERE source_id = '{GONE}'")[0]["is_active"] == 1


def test_default_mode_is_unchanged_by_the_daily_option(db):
    def setup(c):
        seed(c, ALWAYS_RECENT, "상시", ago(1), status="상시")                    # --daily 라면 대상이 아닌 행
    prepare(db, setup)
    fetcher = Fake({1: list_html([(ALWAYS_RECENT, "상시")])})
    stats = run_crawl(fetcher, db, RUN)                                         # daily 없이: 어제 받은 상세도 다시 받는다
    assert fetcher.detail_calls == [ALWAYS_RECENT] and stats.detail_skipped_policy == 0


# ---------------------------------------------------------------- 옵션 조합
@pytest.mark.parametrize("argv", [["--daily", "--reclassify"], ["--daily", "--no-detail"],
                                  ["--daily-plan", "--daily"], ["--daily-plan", "--reclassify"]])
def test_incompatible_option_combinations_exit_with_error(argv, capsys):
    with pytest.raises(SystemExit) as e:
        parse_args(argv)
    assert e.value.code == 2
    assert "함께 쓸 수 없다" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["--daily"], ["--daily", "--headless"], ["--daily", "--detail-limit", "5"],
                                  ["--daily", "--max-pages", "1"], ["--daily-plan"]])
def test_allowed_option_combinations(argv):
    args = parse_args(argv)
    assert args.daily or args.daily_plan


# ---------------------------------------------------------------- --daily-plan (오프라인, 읽기 전용)
def make_plan_db(path):
    c = init_db(path)
    seed_policy_rows(c)
    seed(c, A8, "상시", ago(8), status="상시")
    seed(c, A6, "상시", ago(6), status="상시")
    seed(c, DATED + "0", "2026-10-25 ~ 2026-10-30", RUN)                        # 오늘 받은 상시 외 행
    c.commit()
    c.close()


def test_daily_plan_prints_counts_and_marks_status_changes_as_decided_at_run_time(db, caplog):
    make_plan_db(db)
    with caplog.at_level(logging.INFO):
        assert run_daily_plan(db, RUN) == 0
    text = caplog.text
    assert "활성 행 9건" in text
    assert "(a) 신규(활성, detail_fetched_at NULL): 1건" in text
    assert "(b) 상시 외 매일(dated/end_only/open/unknown): 5건" in text
    assert "(c) 상태 변경: 실행 시 결정(목록을 읽어야 알 수 있음)" in text
    assert "후보 1건 → 상한 200건 적용 1건" in text                              # A8 만 7일 이상
    assert "대상 합계(상태 변경 제외, 중복 제거): 7건" in text
    assert "오늘 이미 상세를 받아 건너뛸 행: 1건 → 지금 --daily 를 돌리면 실제 상세 요청 예상: 6건" in text


def test_daily_plan_never_writes_to_the_db(db, tmp_path):
    make_plan_db(db)
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    os.chmod(db, stat.S_IREAD)                                                  # 파일을 읽기 전용으로: 쓰기를 시도하면 실패한다
    try:
        assert run_daily_plan(db, RUN) == 0
    finally:
        os.chmod(db, stat.S_IREAD | stat.S_IWRITE)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == digest               # 바이트 단위로 그대로
    assert [p.name for p in tmp_path.iterdir()] == ["youth.db"]                # journal 같은 부산물도 없다


def test_daily_plan_does_not_call_init_db(db, monkeypatch):
    make_plan_db(db)

    def boom(*a, **k):
        raise AssertionError("init_db(마이그레이션=쓰기)를 부르면 안 된다")
    monkeypatch.setattr(crawl, "init_db", boom)
    assert run_daily_plan(db, RUN) == 0


def test_daily_plan_with_missing_db_does_not_create_it(db, caplog):
    with caplog.at_level(logging.ERROR):
        assert run_daily_plan(db, RUN) == 2
    assert not db.exists() and "DB 가 없어" in caplog.text


def test_daily_plan_on_old_schema_db_reports_and_does_not_modify(db, caplog):
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE programs (id INTEGER PRIMARY KEY, source_id TEXT, period_type TEXT, "
              "is_active INTEGER, source_status TEXT)")                         # detail_fetched_at 없음
    c.commit()
    c.close()
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    with caplog.at_level(logging.ERROR):
        assert run_daily_plan(db, RUN) == 2
    assert "스키마가 오래되어" in caplog.text
    assert hashlib.sha256(db.read_bytes()).hexdigest() == digest


def test_main_daily_plan_does_not_open_a_browser(db, monkeypatch):
    make_plan_db(db)
    monkeypatch.setattr(crawl, "DB_PATH", db)
    monkeypatch.setattr(crawl, "setup_logging", lambda now: None)
    monkeypatch.setattr(crawl, "make_driver", lambda headless: pytest.fail("브라우저를 열면 안 된다"))
    assert crawl.main(["--daily-plan"]) == 0
