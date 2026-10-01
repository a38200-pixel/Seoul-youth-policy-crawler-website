"""실행 진입점: python -m backend.crawler.crawl [--headless] [--max-pages N] [--no-detail] [--detail-limit N] [--reclassify]"""
import argparse
import logging
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import selectors as sel
from .browser import make_driver
from .db import (count_active, deactivate_unseen, detail_received_today, fetch_all, init_db,
                 reclassify_periods, upsert_program)
from .detail_parser import parse_detail
from .list_parser import parse_list, parse_total_count
from .normalizer import KST
from .record import make_row

log = logging.getLogger("crawl")

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "backend" / "data" / "youth.db"
LOG_DIR = ROOT / "backend" / "logs"

PER_PAGE = 24
MAX_PAGES_CAP = 300     # 무한 루프 방지
MIN_DELAY = 1.0         # 페이지·상세 이동 사이 최소 대기(초)
LIST_WAIT = 60          # 접속 대기열(WebGate) 통과까지 넉넉히
DETAIL_WAIT = 30
MAX_RETRIES = 2
MIN_ACTIVE_RATIO = 0.5  # 직전 활성 공고 수 대비 이 비율 미만이면 is_active 갱신 생략


# ---------------------------------------------------------------- 브라우저 I/O
class SeleniumFetcher:
    """페이지 HTML(page_source)을 가져온다. 실패하면 None."""

    def __init__(self, driver, log_dir=LOG_DIR):
        self.driver = driver
        self.log_dir = Path(log_dir)
        self._last_nav = None

    def _pause(self):
        if self._last_nav is not None:
            remaining = MIN_DELAY - (time.monotonic() - self._last_nav)
            if remaining > 0:
                time.sleep(remaining)

    def _get(self, url, ready_css, timeout):
        for attempt in range(1, MAX_RETRIES + 2):
            self._pause()
            self.driver.get(url)
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ready_css)))
                self._last_nav = time.monotonic()
                return self.driver.page_source
            except TimeoutException:
                self._last_nav = time.monotonic()
                log.warning("대기 타임아웃(%d/%d) %s: %s", attempt, MAX_RETRIES + 1, ready_css, url)
        self._screenshot()
        return None

    def _screenshot(self):
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / f"timeout_{datetime.now(KST):%Y%m%d_%H%M%S}.png"
            self.driver.save_screenshot(str(path))
            log.error("타임아웃으로 스크린샷 저장: %s (현재 URL: %s)", path, self.driver.current_url)
        except Exception:
            log.exception("스크린샷 저장 실패")

    def fetch_list(self, page):
        return self._get(sel.list_url(page=page, per_page=PER_PAGE), sel.LIST_FEED, LIST_WAIT)

    def fetch_detail(self, source_id):
        return self._get(sel.detail_url(source_id), sel.DETAIL_TITLE, DETAIL_WAIT)


# ---------------------------------------------------------------- 판정 로직
@dataclass
class Stats:
    expected_total: int = None
    raw_count: int = 0                 # 목록에서 읽은 공고 수(중복 제거, 제외 전)
    excluded: list = field(default_factory=list)   # [(source_id, title)]
    off_status: int = 0                # 대상 외 모집상태로 건너뛴 수
    collected: int = 0                 # 제외 후 수집 건수
    new: int = 0
    updated: int = 0
    detail_ok: int = 0
    detail_fail: int = 0
    detail_skipped_today: int = 0      # 오늘 이미 받음
    detail_skipped_option: int = 0     # --no-detail / --detail-limit 로 안 받음
    duplicate_ids: list = field(default_factory=list)  # 페이지 사이에 중복으로 나온 source_id
    reached_end: bool = False          # 0건(또는 전부 중복) 페이지를 만나 목록 끝까지 읽었는가
    list_failed: bool = False
    partial_run: bool = False
    deactivated: int = None
    deactivate_note: str = None
    elapsed: float = 0.0
    exit_code: int = 0


def is_excluded(item):
    if item["source_id"] in sel.EXCLUDE_IDS:
        return True
    title = item.get("title") or ""
    return any(k in title for k in sel.EXCLUDE_TITLE_KEYWORDS)


def should_deactivate(partial_run, complete, collected, prev_active):
    """is_active 갱신(deactivate_unseen) 호출 여부와 사유를 반환한다."""
    if partial_run:
        return False, "부분 실행이라 is_active 갱신 생략"
    if not complete:
        return False, "목록을 끝까지 읽지 못해 is_active 갱신 생략"
    if prev_active > 0 and collected < prev_active * MIN_ACTIVE_RATIO:
        return False, (f"수집 {collected}건이 직전 활성 공고 {prev_active}건의 "
                       f"{MIN_ACTIVE_RATIO:.0%} 미만이라 is_active 갱신 생략")
    return True, None


def collect_list(fetcher, max_pages, stats):
    """목록을 pageIndex 순서로 읽어 공고 리스트(중복 제거, 순서 유지)를 반환한다."""
    limit = min(max_pages, MAX_PAGES_CAP) if max_pages else MAX_PAGES_CAP
    items = {}
    for page in range(1, limit + 1):
        html = fetcher.fetch_list(page)
        if html is None:
            log.error("목록 %d페이지를 받지 못함", page)
            stats.list_failed = True
            break
        if page == 1:
            stats.expected_total = parse_total_count(html)
            log.info("예상 건수(전체 N건): %s", stats.expected_total)
        page_items = parse_list(html)
        if not page_items:
            log.info("%d페이지: 항목 0개 → 목록 끝", page)
            stats.reached_end = True
            break
        fresh = [i for i in page_items if i["source_id"] not in items]
        stats.duplicate_ids += [i["source_id"] for i in page_items if i["source_id"] in items]
        log.info("%d페이지: %d건 (이미 본 공고 %d건)", page, len(page_items), len(page_items) - len(fresh))
        if not fresh:
            # 범위를 넘긴 pageIndex 에 마지막 페이지가 반복되는 경우를 대비한 종료 조건
            log.info("%d페이지: 전부 이미 본 공고 → 목록 끝으로 간주", page)
            stats.reached_end = True
            break
        for i in fresh:
            items[i["source_id"]] = i
    else:
        if not max_pages:
            log.warning("페이지 상한 %d 에 도달해 중단(목록 끝 확인 못함)", MAX_PAGES_CAP)
    return list(items.values())


def run_crawl(fetcher, db_path, now, max_pages=None, no_detail=False, detail_limit=None, today=None):
    """수집 전체 흐름. 실행 결과(Stats)를 반환하고 stats.exit_code 가 종료 코드다.

    today: 상세 건너뛰기 판정에 쓰는 '오늘'(date, Asia/Seoul). 생략하면 now 의 날짜. 테스트에서 주입할 수 있다.
    """
    started = time.monotonic()
    stats = Stats(partial_run=max_pages is not None or detail_limit is not None)

    raw = collect_list(fetcher, max_pages, stats)
    stats.raw_count = len(raw)
    if not raw:
        log.error("목록에서 0건을 받았다. DB 를 변경하지 않고 종료한다.")
        stats.exit_code = 2
        stats.elapsed = time.monotonic() - started
        return stats

    targets = []
    for item in raw:
        if is_excluded(item):
            stats.excluded.append((item["source_id"], item["title"]))
            log.info("제외: %s %s", item["source_id"], item["title"])
        elif item["status"] not in sel.TARGET_STATUSES:
            stats.off_status += 1
            log.warning("대상 외 모집상태(%s)라 건너뜀: %s %s", item["status"], item["source_id"], item["title"])
        else:
            targets.append(item)
    stats.collected = len(targets)
    if not targets:
        log.error("제외·상태 필터 후 수집 대상이 0건이다. DB 를 변경하지 않고 종료한다.")
        stats.exit_code = 2
        stats.elapsed = time.monotonic() - started
        return stats

    conn = init_db(db_path)
    try:
        reclassify_and_log(conn, now)  # 목록 수집이 성공한 뒤, upsert 전에 한 번 (목록 0건이면 DB 를 열지 않는다)
        prev_active = count_active(conn)
        if today is None:
            today = now.astimezone(KST).date() if now.tzinfo else now.date()
        fetched = 0
        for item in targets:
            sid = item["source_id"]
            detail = None
            if no_detail:
                stats.detail_skipped_option += 1
            elif detail_received_today(conn, sid, today):
                stats.detail_skipped_today += 1
            elif detail_limit is not None and fetched >= detail_limit:
                stats.detail_skipped_option += 1
            else:
                fetched += 1
                html = fetcher.fetch_detail(sid)
                if html is None:
                    stats.detail_fail += 1
                    log.error("상세 수신 실패: %s %s", sid, item["title"])
                else:
                    try:
                        detail = parse_detail(html)
                        stats.detail_ok += 1
                    except Exception:
                        stats.detail_fail += 1
                        log.exception("상세 파싱 실패: %s", sid)
            if upsert_program(conn, make_row(item, detail), now):
                stats.new += 1
            else:
                stats.updated += 1
            conn.commit()

        seen_ids = [i["source_id"] for i in targets]
        complete = stats.reached_end and not stats.list_failed
        do_it, note = should_deactivate(stats.partial_run, complete, len(seen_ids), prev_active)
        if do_it:
            stats.deactivated = deactivate_unseen(conn, seen_ids)
            conn.commit()
        else:
            stats.deactivate_note = note
            (log.info if stats.partial_run else log.warning)(note)

        if stats.list_failed or (not stats.partial_run and not stats.reached_end):
            stats.exit_code = 1
        stats.elapsed = time.monotonic() - started
        log_summary(conn, stats, set(seen_ids))
    finally:
        conn.close()
    return stats


PERIOD_TYPES = ("dated", "end_only", "always", "unknown")


def format_period_counts(rows):
    types = Counter(r["period_type"] for r in rows)
    return ", ".join(f"{k}={types.get(k, 0)}" for k in PERIOD_TYPES) + f", 미수신={types.get(None, 0)}"


def reclassify_and_log(conn, now):
    """저장된 period_text 로 period_type/start/end 를 다시 계산해 DB 를 갱신하고 결과를 로그로 남긴다."""
    changed = reclassify_periods(conn, now)
    conn.commit()
    log.info("재분류: 바뀐 행 %d건", len(changed))
    for sid, old, new in changed:
        log.info("  %s: %s → %s", sid, old, new)
    log.info("재분류 후 period_type(DB 전체): %s", format_period_counts(fetch_all(conn)))
    return changed


def run_reclassify(db_path, now):
    """--reclassify: 사이트 접속 없이 DB 만 처리한다. 종료 코드를 반환한다."""
    if not Path(db_path).exists():
        log.error("DB 가 없어 재분류할 수 없다: %s", db_path)
        return 2
    conn = init_db(db_path)
    try:
        reclassify_and_log(conn, now)
    finally:
        conn.close()
    return 0


def log_summary(conn, stats, seen_ids):
    rows = [r for r in fetch_all(conn) if r["source_id"] in seen_ids]
    with_detail = [r for r in rows if r["period_type"] is not None]
    optional_empty = {label: sum(1 for r in with_detail if not r[col])
                      for label, col in (("대상", "target"), ("진행일정", "schedule_text"), ("담당기관", "organization"))}
    no_category = [r["title"] for r in rows if not r["category"]]
    unknown = [(r["source_id"], r["period_text"]) for r in rows if r["period_type"] == "unknown"]

    # 목록에서 읽은 공고 = 수집 + 제외 + 대상 외 상태. 예상 건수("전체 N건")와는 이 합계를 비교한다.
    accounted = stats.collected + len(stats.excluded) + stats.off_status
    breakdown = f"수집 {stats.collected} + 제외 {len(stats.excluded)} + 대상 외 {stats.off_status} = {accounted}건"

    out = ["===== 실행 요약 ====="]
    out.append(f"목록 수집: {breakdown} (수집 대상 {stats.collected}건)")
    if stats.partial_run:
        out.append(f"예상 건수 전체 {stats.expected_total}건 / 부분 실행(--max-pages 또는 --detail-limit)이라 비교 생략")
    elif stats.expected_total is None:
        out.append("예상 건수를 읽지 못해 비교 생략")
    elif stats.expected_total != accounted:
        out.append(f"[경고] 예상 건수 {stats.expected_total}건 ≠ {breakdown}")
    else:
        out.append(f"예상 건수 {stats.expected_total}건 = {breakdown}")
    if stats.duplicate_ids:
        out.append(f"[경고] 페이지 간 중복 source_id: {len(stats.duplicate_ids)}건 {stats.duplicate_ids}")
    else:
        out.append("페이지 간 중복 source_id: 없음")
    for sid, title in stats.excluded:
        out.append(f"  제외: {sid} {title}")
    out.append(f"DB: 신규 {stats.new}건 / 갱신 {stats.updated}건")
    out.append(f"상세: 성공 {stats.detail_ok} / 실패 {stats.detail_fail} / "
               f"건너뜀(오늘 받음) {stats.detail_skipped_today} / 건너뜀(옵션) {stats.detail_skipped_option}")
    out.append("period_type: " + format_period_counts(rows))
    out.append(f"선택 필드 비어 있음(상세 받은 {len(with_detail)}건 중): " +
               ", ".join(f"{k} {v}건" for k, v in optional_empty.items()))
    out.append(f"분야 비어 있음: {len(no_category)}건")
    for t in no_category:
        out.append(f"  - {t}")
    out.append(f"unknown 신청기간 원문: {len(unknown)}건")
    for sid, text in unknown:
        out.append(f"  - {sid}: {text!r}")
    if stats.deactivated is not None:
        out.append(f"is_active 갱신: 새로 비활성 {stats.deactivated}건")
    else:
        out.append(f"is_active 갱신 생략: {stats.deactivate_note}")
    out.append(f"소요 시간: {stats.elapsed:.1f}초")
    for line in out:
        log.info(line)


# ---------------------------------------------------------------- CLI
def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="python -m backend.crawler.crawl", description="청년몽땅정보통 크롤러")
    p.add_argument("--headless", action="store_true", help="브라우저 창 없이 실행")
    p.add_argument("--max-pages", type=int, default=None, help="최대 페이지 수(테스트용, 부분 실행)")
    p.add_argument("--no-detail", action="store_true", help="상세 페이지 방문 생략")
    p.add_argument("--detail-limit", type=int, default=None, help="상세를 받을 최대 건수(부분 실행)")
    p.add_argument("--reclassify", action="store_true",
                   help="사이트 접속 없이 DB 의 period_text 로 period_type/start/end 를 다시 계산")
    args = p.parse_args(argv)
    if args.max_pages is not None and args.max_pages < 1:
        p.error("--max-pages 는 1 이상이어야 한다")
    if args.detail_limit is not None and args.detail_limit < 0:
        p.error("--detail-limit 는 0 이상이어야 한다")
    return args


def setup_logging(now):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(LOG_DIR / f"crawl_{now:%Y%m%d}.log", encoding="utf-8")
    console = logging.StreamHandler(sys.stdout)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    for h in (file_handler, console):
        h.setFormatter(fmt)
        root.addHandler(h)


def main(argv=None):
    args = parse_args(argv)
    now = datetime.now(KST)
    setup_logging(now)
    log.info("시작: %s", vars(args))
    if args.reclassify:
        return run_reclassify(DB_PATH, now)
    driver = make_driver(args.headless)
    try:
        stats = run_crawl(SeleniumFetcher(driver), DB_PATH, now, max_pages=args.max_pages,
                          no_detail=args.no_detail, detail_limit=args.detail_limit)
    except Exception:
        log.exception("치명적 오류")
        return 3
    finally:
        driver.quit()
    return stats.exit_code


if __name__ == "__main__":
    sys.exit(main())
