"""API 의 DB 조회. 요청마다 file:...?mode=ro 로 읽기 전용으로 연다.

쓰기, init_db, 마이그레이션은 하지 않는다(이 모듈에는 SELECT 만 있다). 표시 규칙은 backend/service/display.py 가 담당한다.
"""
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from backend.crawler.db import to_seoul_date
from backend.crawler.normalizer import KST

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "backend" / "data" / "youth.db"
ENV_DB_PATH = "YOUTH_DB_PATH"


class DatabaseUnavailable(Exception):
    """DB 파일이 없거나 읽기 전용으로 열 수 없다. API 는 503 으로 응답한다(DB 를 만들지 않는다)."""


def get_db_path():
    """환경변수 YOUTH_DB_PATH, 없으면 backend/data/youth.db. 요청마다 읽는다."""
    return Path(os.environ.get(ENV_DB_PATH) or DEFAULT_DB_PATH)


def connect_readonly(path=None):
    path = Path(path) if path else get_db_path()
    if not path.is_file():
        raise DatabaseUnavailable(f"DB 파일이 없다: {path}")
    try:
        # check_same_thread=False: FastAPI 가 동기 의존성·엔드포인트를 스레드풀의 서로 다른 스레드에서 실행한다.
        # 연결은 요청 하나가 단독으로 쓰고 요청이 끝나면 닫으므로 공유되지 않는다.
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)
    except sqlite3.OperationalError as e:
        raise DatabaseUnavailable(f"DB 를 읽기 전용으로 열 수 없다: {e}") from e
    conn.row_factory = sqlite3.Row
    return conn


def aware(value):
    """isoformat 문자열 → 서울 시간대의 aware datetime(정렬·최댓값 비교용). 시간대가 없으면 서울 시각으로 본다."""
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=KST) if dt.tzinfo is None else dt.astimezone(KST)


def within_days(detected_at, today, days):
    """detected_at 의 서울 날짜가 today 로부터 days 일 이내(<=)인지. badges/is_new 와 같은 경계."""
    d = to_seoul_date(detected_at)
    return d is not None and (today - d).days <= days


def active_rows(conn):
    return conn.execute("SELECT * FROM programs WHERE is_active = 1").fetchall()


def get_program(conn, source_id):
    return conn.execute("SELECT * FROM programs WHERE source_id = ?", (source_id,)).fetchone()


def program_history(conn, source_id):
    """한 공고의 전체 변경 이력, 최신순."""
    return conn.execute(
        "SELECT id, source_id, change_type, old_value, new_value, reason, detected_at "
        "FROM program_changes WHERE source_id = ? ORDER BY detected_at DESC, id DESC", (source_id,)).fetchall()


def recent_events(conn, today, window_days):
    """최근 window_days 일의 이벤트(제목 포함)를 **한 번의 쿼리**로 가져온다(N+1 방지).

    시간대 환산 여유로 하루 더 넓게 가져오므로, 정확한 경계 판정은 호출하는 쪽(within_days/badges)이 한다.
    """
    since = (today - timedelta(days=window_days + 1)).isoformat()
    return conn.execute(
        "SELECT c.id, c.source_id, c.change_type, c.old_value, c.new_value, c.reason, c.detected_at, p.title "
        "FROM program_changes c LEFT JOIN programs p ON p.source_id = c.source_id "
        "WHERE c.detected_at >= ? ORDER BY c.detected_at DESC, c.id DESC", (since,)).fetchall()


def events_by_source(events):
    grouped = defaultdict(list)
    for e in events:
        grouped[e["source_id"]].append(e)
    return grouped


def last_collected_at(conn):
    """활성 행의 last_seen_at 최댓값(isoformat). 목록 수집 때만 갱신되는 값이다.

    updated_at(재분류도 갱신)·detail_fetched_at(상세를 받은 행만 갱신)은 '마지막 수집'이 아니라서 쓰지 않는다.
    활성 행이 없거나 last_seen_at 이 전부 NULL 이면 None.
    """
    values = [r["last_seen_at"] for r in conn.execute(
        "SELECT last_seen_at FROM programs WHERE is_active = 1 AND last_seen_at IS NOT NULL")]
    return max(values, key=aware) if values else None
