"""crawl.py 의 수집·판정 로직 테스트. 브라우저 대신 가짜 fetcher 와 samples HTML 을 쓴다(네트워크 없음)."""
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.crawler import crawl
from backend.crawler.crawl import is_excluded, parse_args, run_crawl, should_deactivate
from backend.crawler.db import init_db, upsert_program
from backend.crawler.record import make_row

SAMPLES = Path(__file__).resolve().parent.parent / "backend" / "crawler" / "samples"
LIST_SAMPLE = (SAMPLES / "list_sample.html").read_text(encoding="utf-8")
DETAIL_SAMPLE = (SAMPLES / "detail_sample.html").read_text(encoding="utf-8")
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=KST)
LATER = NOW + timedelta(hours=1)
EMPTY = "<html><body><div class='category-feed'></div></body></html>"


def list_html(ids, status="모집중"):
    items = "".join(
        f'<div class="feed-item"><a class="item-overlay" onclick="goView(\'{i}\');"></a>'
        f'<div class="content"><span class="cate">금융</span><div class="name">공고{i}</div>'
        f'<span class="state">{status}</span></div></div>' for i in ids)
    return f'<html><body><div class="category-feed">{items}</div></body></html>'


class FakeFetcher:
    def __init__(self, pages, detail_html=DETAIL_SAMPLE, fail_detail=()):
        self.pages = pages              # {page: html | None}
        self.detail_html = detail_html
        self.fail_detail = set(fail_detail)
        self.list_calls, self.detail_calls = [], []

    def fetch_list(self, page):
        self.list_calls.append(page)
        return self.pages.get(page, EMPTY)

    def fetch_detail(self, source_id):
        self.detail_calls.append(source_id)
        return None if source_id in self.fail_detail else self.detail_html


@pytest.fixture
def db(tmp_path):
    return tmp_path / "youth.db"


def rows(db_path, where="1=1"):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    try:
        return c.execute(f"SELECT * FROM programs WHERE {where}").fetchall()
    finally:
        c.close()


def seed_active(db_path, n):
    conn = init_db(db_path)
    for i in range(n):
        upsert_program(conn, make_row({"source_id": f"old{i}", "title": "t", "category": "c", "status": "상시"}, None), NOW)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- 순수 함수
def test_is_excluded():
    assert is_excluded({"source_id": "68721", "title": "아무 제목"})
    assert is_excluded({"source_id": "1", "title": "📢 프로그램 게시요청 가이드 📢"})
    assert not is_excluded({"source_id": "1", "title": "정상 공고"})
    assert not is_excluded({"source_id": "1", "title": None})


def test_should_deactivate_rules():
    assert should_deactivate(True, True, 100, 100)[0] is False                  # 부분 실행
    assert "부분 실행이라 is_active 갱신 생략" in should_deactivate(True, True, 100, 100)[1]
    assert should_deactivate(False, False, 100, 100)[0] is False                # 끝까지 못 읽음
    assert should_deactivate(False, True, 49, 100)[0] is False                  # 50% 미만
    assert should_deactivate(False, True, 50, 100)[0] is True                   # 정확히 50%
    assert should_deactivate(False, True, 3, 0) == (True, None)                 # 첫 전체 실행은 검사 생략


def test_parse_args():
    a = parse_args(["--headless", "--max-pages", "2", "--no-detail", "--detail-limit", "5"])
    assert (a.headless, a.max_pages, a.no_detail, a.detail_limit) == (True, 2, True, 5)
    d = parse_args([])
    assert (d.headless, d.max_pages, d.no_detail, d.detail_limit) == (False, None, False, None)
    with pytest.raises(SystemExit):
        parse_args(["--max-pages", "0"])


# ---------------------------------------------------------------- 목록 수집·제외
def test_full_run_with_list_sample(db, caplog):
    fetcher = FakeFetcher({1: LIST_SAMPLE})
    with caplog.at_level(logging.INFO):
        stats = run_crawl(fetcher, db, NOW)
    assert fetcher.list_calls == [1, 2]            # 2페이지(0건)에서 종료
    assert stats.expected_total == 9254 and stats.raw_count == 8
    assert stats.excluded == [("68721", "📢 프로그램 게시요청 가이드 📢")]
    assert stats.collected == 7 and len(rows(db)) == 7
    assert not rows(db, "source_id = '68721'")
    assert "제외: 68721" in caplog.text
    assert "예상 건수 9254건 ≠ 수집 7 + 제외 1 + 대상 외 0 = 8건" in caplog.text
    assert stats.new == 7 and stats.updated == 0
    assert stats.detail_ok == 7 and stats.exit_code == 0
    assert stats.deactivated == 0                  # 첫 전체 실행


def test_summary_contains_required_items(db, caplog):
    with caplog.at_level(logging.INFO):
        run_crawl(FakeFetcher({1: list_html(["1", "2"])}), db, NOW)
    for text in ("실행 요약", "신규 2건", "상세: 성공 2",
                 "period_type: dated=2, end_only=0, always=0, unknown=0, 미수신=0",
                 # detail_sample.html 은 대상·진행일정·담당기관이 모두 채워져 있다
                 "선택 필드 비어 있음(상세 받은 2건 중): 대상 0건, 진행일정 0건, 담당기관 0건",
                 "분야 비어 있음: 0건", "unknown 신청기간 원문: 0건", "소요 시간"):
        assert text in caplog.text, text


TOTAL_TAB = ('<div class="tab-st4"><ul class="tab-btn"><li class="active"><a>최신순</a></li></ul></div>'
             '<div class="tab-st4"><ul class="tab-btn"><li class="active"><a>전체 {n}건</a></li></ul></div>')


def test_count_comparison_uses_collected_plus_excluded(db, caplog):
    # 목록 3건 중 1건(68721)은 제외 → 수집 2 + 제외 1 = 3 이 예상 건수 3 과 같아야 한다
    page = TOTAL_TAB.format(n=3) + list_html(["1", "2", "68721"])
    with caplog.at_level(logging.INFO):
        run_crawl(FakeFetcher({1: page}), db, NOW)
    assert "예상 건수 3건 = 수집 2 + 제외 1 + 대상 외 0 = 3건" in caplog.text
    assert "[경고] 예상 건수" not in caplog.text


def test_count_mismatch_warns(db, caplog):
    page = TOTAL_TAB.format(n=10) + list_html(["1", "2", "68721"])
    with caplog.at_level(logging.INFO):
        run_crawl(FakeFetcher({1: page}), db, NOW)
    assert "[경고] 예상 건수 10건 ≠ 수집 2 + 제외 1 + 대상 외 0 = 3건" in caplog.text


def test_duplicate_ids_reported_in_summary(db, caplog):
    pages = {1: list_html(["1", "2"]), 2: list_html(["2", "3"])}
    with caplog.at_level(logging.INFO):
        stats = run_crawl(FakeFetcher(pages), db, NOW)
    assert stats.duplicate_ids == ["2"]
    assert "페이지 간 중복 source_id: 1건 ['2']" in caplog.text


def test_no_duplicates_reported_as_none(db, caplog):
    with caplog.at_level(logging.INFO):
        run_crawl(FakeFetcher({1: list_html(["1", "2"])}), db, NOW)
    assert "페이지 간 중복 source_id: 없음" in caplog.text


END_ONLY_DETAIL = (SAMPLES / "detail_sample_endonly.html").read_text(encoding="utf-8")


def test_summary_counts_empty_optional_fields_per_field(db, caplog):
    # 상세 샘플은 대상이 비어 있다 → 건별 WARNING 없이 요약에 필드별 건수로만 나온다
    with caplog.at_level(logging.INFO):
        run_crawl(FakeFetcher({1: list_html(["1", "2", "3"])}, detail_html=END_ONLY_DETAIL), db, NOW)
    assert "선택 필드 비어 있음(상세 받은 3건 중): 대상 3건, 진행일정 0건, 담당기관 0건" in caplog.text
    assert "period_type: dated=0, end_only=3, always=0, unknown=0, 미수신=0" in caplog.text
    assert not [r for r in caplog.records if "값 비어 있음" in r.getMessage()]


def test_reclassify_runs_automatically_at_start_of_normal_run(db, caplog):
    conn = init_db(db)
    conn.execute(
        "INSERT INTO programs (source_id, period_text, period_type, is_active) "
        "VALUES ('old', '~ 2026-10-08 00 : 00', 'unknown', 1)")
    conn.commit()
    conn.close()
    with caplog.at_level(logging.INFO):
        run_crawl(FakeFetcher({1: list_html(["1"])}), db, NOW, max_pages=1)
    assert "재분류: 바뀐 행 1건" in caplog.text
    assert rows(db, "source_id = 'old'")[0]["period_type"] == "end_only"


def test_zero_items_run_does_not_reclassify_or_touch_db(db):
    conn = init_db(db)
    conn.execute("INSERT INTO programs (source_id, period_text, period_type) VALUES ('old', '~ 2026-10-08', 'unknown')")
    conn.commit()
    conn.close()
    assert run_crawl(FakeFetcher({1: EMPTY}), db, NOW).exit_code == 2
    assert rows(db, "source_id = 'old'")[0]["period_type"] == "unknown"   # 목록 0건이면 DB 를 건드리지 않는다


def test_reclassify_mode_without_db_file(db, caplog):
    with caplog.at_level(logging.ERROR):
        assert crawl.run_reclassify(db, NOW) == 2
    assert not db.exists()          # DB 를 새로 만들지 않는다
    assert "DB 가 없어" in caplog.text


def test_reclassify_mode_updates_db_and_reports(db, caplog):
    conn = init_db(db)
    conn.execute("INSERT INTO programs (source_id, period_text, period_type) VALUES ('a', '~ 2026-10-08', 'unknown')")
    conn.execute("INSERT INTO programs (source_id, period_text, period_type) VALUES ('b', NULL, NULL)")
    conn.commit()
    conn.close()
    with caplog.at_level(logging.INFO):
        assert crawl.run_reclassify(db, NOW) == 0
    assert "재분류: 바뀐 행 1건" in caplog.text
    assert "a: ('unknown', None, None) → ('end_only', None, '2026-10-08')" in caplog.text
    assert "dated=0, end_only=1, always=0, unknown=0, 미수신=1" in caplog.text
    assert rows(db, "source_id = 'b'")[0]["period_type"] is None


def test_main_reclassify_flag_does_not_open_browser(db, monkeypatch):
    monkeypatch.setattr(crawl, "DB_PATH", db)
    monkeypatch.setattr(crawl, "setup_logging", lambda now: None)
    monkeypatch.setattr(crawl, "make_driver", lambda headless: pytest.fail("브라우저를 열면 안 된다"))
    assert crawl.main(["--reclassify"]) == 2    # DB 없음 → 2, 브라우저는 열리지 않음


def test_off_status_items_are_skipped(db):
    pages = {1: list_html(["1", "2"], status="마감")}
    stats = run_crawl(FakeFetcher(pages), db, NOW)
    assert stats.off_status == 2 and stats.exit_code == 2
    assert not db.exists()


def test_duplicate_ids_across_pages_are_collapsed(db):
    pages = {1: list_html(["1", "2"]), 2: list_html(["2", "3"])}
    stats = run_crawl(FakeFetcher(pages), db, NOW)
    assert stats.raw_count == 3 and len(rows(db)) == 3


def test_repeated_last_page_ends_the_list(db):
    pages = {1: list_html(["1", "2"]), 2: list_html(["1", "2"]), 3: list_html(["1", "2"])}
    fetcher = FakeFetcher(pages)
    stats = run_crawl(fetcher, db, NOW)
    assert fetcher.list_calls == [1, 2]
    assert stats.reached_end and stats.exit_code == 0


def test_page_cap_stops_runaway_and_skips_deactivate(db, monkeypatch):
    monkeypatch.setattr(crawl, "MAX_PAGES_CAP", 3)
    seed_active(db, 1)
    pages = {p: list_html([str(p * 10 + 1), str(p * 10 + 2)]) for p in range(1, 10)}  # 페이지마다 다른 숫자 ID
    fetcher = FakeFetcher(pages)
    stats = run_crawl(fetcher, db, NOW)
    assert fetcher.list_calls == [1, 2, 3]
    assert stats.reached_end is False and stats.exit_code == 1
    assert stats.deactivated is None
    assert rows(db, "source_id = 'old0'")[0]["is_active"] == 1


# ---------------------------------------------------------------- 0건·실패
def test_zero_items_does_not_touch_db(db, caplog):
    seed_active(db, 3)
    before = [tuple(r) for r in rows(db)]
    with caplog.at_level(logging.ERROR):
        stats = run_crawl(FakeFetcher({1: EMPTY}), db, NOW)
    assert stats.exit_code == 2
    assert "0건" in caplog.text
    assert [tuple(r) for r in rows(db)] == before


def test_zero_items_creates_no_db_file(db):
    stats = run_crawl(FakeFetcher({1: EMPTY}), db, NOW)
    assert stats.exit_code == 2 and not db.exists()


def test_first_page_failure_creates_no_db_file(db):
    stats = run_crawl(FakeFetcher({1: None}), db, NOW)
    assert stats.exit_code == 2 and stats.list_failed and not db.exists()


def test_later_page_failure_keeps_data_but_skips_deactivate(db):
    seed_active(db, 1)
    stats = run_crawl(FakeFetcher({1: list_html(["1", "2"]), 2: None}), db, NOW)
    assert stats.list_failed and stats.exit_code == 1
    assert stats.deactivated is None
    assert len(rows(db, "source_id IN ('1','2')")) == 2
    assert rows(db, "source_id = 'old0'")[0]["is_active"] == 1


# ---------------------------------------------------------------- is_active 갱신 규칙
def test_partial_run_never_deactivates(db, caplog):
    seed_active(db, 1)
    fetcher = FakeFetcher({1: list_html(["1", "2"])})
    with caplog.at_level(logging.INFO):
        stats = run_crawl(fetcher, db, NOW, max_pages=1)
    assert fetcher.list_calls == [1]
    assert stats.deactivated is None and stats.exit_code == 0
    assert rows(db, "source_id = 'old0'")[0]["is_active"] == 1
    assert "부분 실행이라 is_active 갱신 생략" in caplog.text


def test_detail_limit_is_partial_run(db):
    seed_active(db, 1)
    stats = run_crawl(FakeFetcher({1: list_html(["1", "2"])}), db, NOW, detail_limit=1)
    assert stats.partial_run and stats.deactivated is None
    assert rows(db, "source_id = 'old0'")[0]["is_active"] == 1


def test_full_run_deactivates_unseen(db):
    seed_active(db, 1)
    stats = run_crawl(FakeFetcher({1: list_html(["1", "2"])}), db, NOW)
    assert stats.deactivated == 1
    assert rows(db, "source_id = 'old0'")[0]["is_active"] == 0
    assert len(rows(db)) == 3  # 삭제하지 않는다


def test_under_50_percent_skips_deactivate(db, caplog):
    seed_active(db, 20)
    with caplog.at_level(logging.WARNING):
        stats = run_crawl(FakeFetcher({1: list_html(["1", "2"])}), db, NOW)
    assert stats.deactivated is None
    assert "50% 미만" in caplog.text
    assert all(r["is_active"] == 1 for r in rows(db, "source_id LIKE 'old%'"))


# ---------------------------------------------------------------- 상세 수신
def test_second_run_skips_details_received_today(db):
    first = FakeFetcher({1: list_html(["1", "2", "3"])})
    run_crawl(first, db, NOW)
    assert len(first.detail_calls) == 3

    second = FakeFetcher({1: list_html(["1", "2", "3"])})
    stats = run_crawl(second, db, LATER)
    assert second.detail_calls == []
    assert stats.detail_skipped_today == 3 and stats.detail_ok == 0
    assert stats.new == 0 and stats.updated == 3
    assert len(rows(db)) == 3
    assert all(r["last_seen_at"] == LATER.isoformat() for r in rows(db))
    assert all(r["first_seen_at"] == NOW.isoformat() for r in rows(db))
    assert all(r["period_type"] == "dated" for r in rows(db))  # 상세 값 유지


def test_yesterdays_details_are_refetched_even_after_a_list_only_run_today(db):
    # 어제 상세를 받은 뒤, 오늘 목록만 본 실행(last_seen_at 이 오늘로 갱신됨)이 있어도 상세는 재방문해야 한다
    day1, day2 = NOW, NOW + timedelta(days=1)
    run_crawl(FakeFetcher({1: list_html(["1", "2"])}), db, day1)
    run_crawl(FakeFetcher({1: list_html(["1", "2"])}), db, day2, no_detail=True)
    assert all(r["last_seen_at"].startswith("2026-10-02") for r in rows(db))   # 목록 upsert 로 오늘이 됨
    assert all(r["detail_fetched_at"] == day1.isoformat() for r in rows(db))   # 상세 시각은 그대로(어제)

    fetcher = FakeFetcher({1: list_html(["1", "2"])})
    run_crawl(fetcher, db, day2 + timedelta(hours=1))
    assert fetcher.detail_calls == ["1", "2"]


def test_skip_decision_uses_injected_today_and_detail_fetched_at(db):
    day2 = NOW + timedelta(days=1)
    page = {1: list_html(["1", "2"])}
    run_crawl(FakeFetcher(page), db, NOW)                                  # detail_fetched_at = 2026-10-01

    tomorrow = FakeFetcher(page)
    run_crawl(tomorrow, db, day2, today=date(2026, 10, 2))                 # 어제(10-01) 받은 상세 → 재방문
    assert tomorrow.detail_calls == ["1", "2"]                             # 이제 detail_fetched_at = 2026-10-02

    same_day = FakeFetcher(page)
    stats = run_crawl(same_day, db, day2 + timedelta(hours=2), today=date(2026, 10, 2))   # 오늘(10-02) 받음 → 건너뜀
    assert same_day.detail_calls == [] and stats.detail_skipped_today == 2

    other_day = FakeFetcher(page)
    stats = run_crawl(other_day, db, day2 + timedelta(hours=3), today=date(2026, 10, 1))  # 주입한 오늘이 10-01 이면 10-02 에 받은 건 오늘이 아님
    assert other_day.detail_calls == ["1", "2"] and stats.detail_skipped_today == 0


def test_failed_detail_does_not_refresh_detail_fetched_at(db):
    run_crawl(FakeFetcher({1: list_html(["1"])}), db, NOW)
    next_day = NOW + timedelta(days=1)
    run_crawl(FakeFetcher({1: list_html(["1"])}, fail_detail=["1"]), db, next_day)
    r = rows(db, "source_id = '1'")[0]
    assert r["detail_fetched_at"] == NOW.isoformat()          # 실패했으니 그대로
    assert r["last_seen_at"] == next_day.isoformat()          # 목록 upsert 만 갱신
    # 같은 날 다시 돌리면 실패했던 상세를 재시도한다(어제 값을 오늘 받은 것으로 보지 않는다)
    retry = FakeFetcher({1: list_html(["1"])})
    run_crawl(retry, db, next_day + timedelta(hours=1))
    assert retry.detail_calls == ["1"]


def test_details_are_fetched_again_on_next_day(db):
    run_crawl(FakeFetcher({1: list_html(["1"])}), db, NOW)
    fetcher = FakeFetcher({1: list_html(["1"])})
    run_crawl(fetcher, db, NOW + timedelta(days=1))
    assert fetcher.detail_calls == ["1"]


def test_detail_limit_counts_only_fetches(db):
    fetcher = FakeFetcher({1: list_html(["1", "2", "3", "4"])})
    stats = run_crawl(fetcher, db, NOW, detail_limit=2)
    assert fetcher.detail_calls == ["1", "2"]
    assert stats.detail_ok == 2 and stats.detail_skipped_option == 2
    assert len(rows(db)) == 4
    assert [r["period_type"] for r in rows(db, "source_id IN ('3','4')")] == [None, None]


def test_no_detail_never_fetches(db):
    fetcher = FakeFetcher({1: list_html(["1", "2"])})
    stats = run_crawl(fetcher, db, NOW, no_detail=True)
    assert fetcher.detail_calls == [] and stats.detail_skipped_option == 2
    assert all(r["period_type"] is None for r in rows(db))   # 'unknown' 이 아니라 None


def test_detail_failure_still_saves_list_row(db):
    fetcher = FakeFetcher({1: list_html(["1", "2"])}, fail_detail=["2"])
    stats = run_crawl(fetcher, db, NOW)
    assert stats.detail_ok == 1 and stats.detail_fail == 1
    r = rows(db, "source_id = '2'")[0]
    assert r["title"] == "공고2" and r["period_type"] is None
