"""읽기 전용 API 테스트. TestClient + 임시 DB, today=2026-10-02 고정. 실제 DB·네트워크는 쓰지 않는다."""
import hashlib
import os
import shutil
import sqlite3
import stat
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api import main, queries
from backend.api.main import app, get_today
from backend.crawler.db import deactivate_unseen, init_db, upsert_program
from backend.crawler.record import make_row

TODAY = date(2026, 10, 2)
KST = timezone(timedelta(hours=9))
D1 = datetime(2026, 10, 1, 9, 0, tzinfo=KST)         # 기준일: 이날 처음 본 행은 NEW 가 아니다
D1B = D1 + timedelta(hours=1)
D2E = datetime(2026, 10, 2, 7, 0, tzinfo=KST)
D2F = datetime(2026, 10, 2, 7, 30, tzinfo=KST)
D2 = datetime(2026, 10, 2, 9, 0, tzinfo=KST)
D2L = datetime(2026, 10, 2, 10, 0, tzinfo=KST)

ITEM_FIELDS = {"source_id", "title", "category", "organization", "display_status", "group", "d_day", "d_day_label",
               "source_status", "period_text", "start_date", "end_date", "apply_url", "source_url", "first_seen_at", "badges"}
EXPECTED_DEADLINE = ["102", "103", "130", "101", "122", "131", "104", "106"]


def put(c, sid, period_text, now, status="모집중", category="금융", org="서울시", **extra):
    list_item = {"source_id": sid, "title": f"공고{sid}", "category": category, "status": status}
    detail = {"title": f"공고{sid}", "category": category, "organization": org, "period_text": period_text,
              "apply_url": f"https://apply.example/{sid}", "summary": f"요약{sid}", "target": "청년",
              "schedule_text": "2026-01-01 ~ 2026-01-02", **extra}
    upsert_program(c, make_row(list_item, detail), now)


def build_db(path):
    """다양한 유형의 행과 실제로 생성된 변경 이벤트가 있는 임시 DB."""
    c = init_db(path)
    put(c, "101", "2026-09-20 ~ 2026-10-05", D1)                                  # 나중에 연장됨
    put(c, "102", "2026-09-20 ~ 2026-10-02", D1)                                  # D-Day
    put(c, "103", "2026-09-20 ~ 2026-10-03", D1, status="모집예정", category="주거")    # 나중에 상태가 바뀜
    put(c, "104", "2026-10-12 ~ 2026-10-21", D1, status="모집중", org="마포구청")        # 시작일 미래인데 사이트는 모집중
    put(c, "105", "2026-09-20 ~ 2026-10-01", D1)                                  # 활성이지만 마감 지남(expired)
    put(c, "106", "2026-09-20 ~ 00 : 00 [ 선착순 마감 ]", D1, category="주거")           # open
    put(c, "107", "상시", D1, status="상시", category="금융")
    put(c, "108", "상시", D1, status="상시", category="교육")
    put(c, "109", "상시", D1, status="상시", category=None)                         # 상시-기타
    put(c, "110", "추후 공지", D1)                                                 # unknown
    put(c, "120", "2026-09-20 ~ 2026-10-20", D1)                                  # 나중에 비활성(early)
    put(c, "121", "2026-09-20 ~ 2026-10-01", D1)                                  # 나중에 비활성(expired)
    put(c, "122", "2026-09-20 ~ 2026-10-30", D1)                                  # 비활성 후 재등록
    all_ids = ["101", "102", "103", "104", "105", "106", "107", "108", "109", "110", "120", "121", "122"]
    deactivate_unseen(c, [i for i in all_ids if i != "122"], D1B)                  # 122: deactivated(early)
    put(c, "130", "2026-09-25 ~ 2026-10-07", D2E, category="교육")                  # 기준일 다음 날 처음 봄 → NEW
    put(c, "131", "2026-10-05 ~ 00 : 00 [ 선착순 마감 ]", D2F, category="주거")         # open, 시작일 미래 → NEW
    put(c, "101", "2026-09-20 ~ 2026-10-08", D2)                                  # extended
    put(c, "103", "2026-09-20 ~ 2026-10-03", D2, status="모집중", category="주거")      # status_changed
    put(c, "122", "2026-09-20 ~ 2026-10-30", D2)                                  # reactivated
    deactivate_unseen(c, [i for i in all_ids + ["130", "131"] if i not in ("120", "121")], D2L)   # deactivated 120, 121
    c.commit()
    c.close()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "youth.db"
    build_db(path)
    return path


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setenv("YOUTH_DB_PATH", str(db))
    app.dependency_overrides[get_today] = lambda: TODAY
    yield TestClient(app)
    app.dependency_overrides.clear()


def ids(resp):
    assert resp.status_code == 200, resp.text
    return [i["source_id"] for i in resp.json()["items"]]


def by_id(resp, sid):
    return next(i for i in resp.json()["items"] if i["source_id"] == sid)


# ---------------------------------------------------------------- /api/programs: 탭, 순서, counts
def test_default_tab_is_deadline_with_display_order(client):
    r = client.get("/api/programs")
    assert ids(r) == EXPECTED_DEADLINE            # 모집중(D-Day→…) → 모집예정(시작일순) → 마감일 미정
    body = r.json()
    assert body["total"] == 8
    assert body["counts"] == {"deadline": 8, "always": 2, "etc": 1}


def test_always_etc_and_all_tabs(client):
    assert ids(client.get("/api/programs?tab=always")) == ["108", "107"]          # 분야순(교육 < 금융)
    assert ids(client.get("/api/programs?tab=etc")) == ["109"]
    r = client.get("/api/programs?tab=all")
    assert ids(r) == EXPECTED_DEADLINE + ["108", "107", "109", "110"]              # unknown 포함
    assert r.json()["total"] == 12
    assert by_id(r, "110")["display_status"] == "확인 필요"


def test_expired_and_inactive_rows_are_not_listed(client):
    everything = ids(client.get("/api/programs?tab=all&limit=200"))
    assert "105" not in everything                 # 활성이지만 마감 지남
    assert "120" not in everything and "121" not in everything   # 비활성


def test_invalid_tab_is_rejected(client):
    assert client.get("/api/programs?tab=nope").status_code == 422


def test_item_has_exactly_the_documented_fields(client):
    item = client.get("/api/programs").json()["items"][0]
    assert set(item) == ITEM_FIELDS
    assert (item["source_id"], item["display_status"], item["d_day_label"], item["group"]) == \
        ("102", "모집중", "D-Day", "recruiting")


def test_future_start_recruiting_row_is_listed_as_upcoming_and_source_status_is_kept(client):
    item = by_id(client.get("/api/programs"), "104")
    assert (item["display_status"], item["d_day"], item["d_day_label"], item["group"]) == ("모집예정", 10, "시작 D-10", "upcoming")
    assert item["source_status"] == "모집중"                                         # 사이트 상태는 그대로


def test_open_with_future_start_is_upcoming_too(client):
    item = by_id(client.get("/api/programs"), "131")
    assert (item["display_status"], item["d_day_label"]) == ("모집예정", "시작 D-3")


# ---------------------------------------------------------------- limit / offset
def test_limit_and_offset_paginate_after_sorting(client):
    r = client.get("/api/programs?limit=3&offset=2")
    assert ids(r) == ["130", "101", "122"]                                          # 정렬된 전체의 3~5번째
    assert r.json()["total"] == 8
    assert ids(client.get("/api/programs?limit=3&offset=6")) == ["104", "106"]
    assert ids(client.get("/api/programs?offset=100")) == []


@pytest.mark.parametrize("query, status", [("limit=0", 422), ("limit=201", 422), ("limit=200", 200), ("offset=-1", 422)])
def test_limit_and_offset_bounds(client, query, status):
    assert client.get(f"/api/programs?{query}").status_code == status


# ---------------------------------------------------------------- q / category 필터
def test_q_matches_title_organization_and_category_partially(client):
    assert ids(client.get("/api/programs?q=공고101")) == ["101"]                     # 제목
    assert ids(client.get("/api/programs?q=마포")) == ["104"]                         # 기관(부분 일치)
    r = client.get("/api/programs?tab=all&q=교육")                                    # 분야
    assert ids(r) == ["130", "108"]
    assert r.json()["counts"] == {"deadline": 1, "always": 1, "etc": 0}               # counts 는 q 적용 후 탭별 건수


def test_category_filter(client):
    r = client.get("/api/programs?tab=all&category=주거")
    assert ids(r) == ["103", "131", "106"]
    assert r.json()["total"] == 3 and r.json()["counts"] == {"deadline": 3, "always": 0, "etc": 0}
    assert ids(client.get("/api/programs?tab=all&category=없는분야")) == []


def test_q_and_category_combine(client):
    assert ids(client.get("/api/programs?tab=all&category=주거&q=공고13")) == ["131"]
    assert ids(client.get("/api/programs?tab=all&category=금융&q=공고13")) == []      # 분야가 다르면 제외


# ---------------------------------------------------------------- 배지
def test_badges_in_list(client):
    r = client.get("/api/programs?tab=all")
    assert [b["type"] for b in by_id(r, "130")["badges"]] == ["new"]
    assert by_id(r, "101")["badges"][0]["detail"] == "2026-10-05 → 2026-10-08"
    assert [b["label"] for b in by_id(r, "101")["badges"]] == ["연장"]
    assert [(b["label"], b["detail"]) for b in by_id(r, "103")["badges"]] == [("상태 변경", "모집예정 → 모집중")]
    assert [b["label"] for b in by_id(r, "122")["badges"]] == ["재등록"]               # deactivated 는 배지가 아니다
    assert by_id(r, "102")["badges"] == [] and by_id(r, "104")["badges"] == []


def test_badges_use_one_events_query_not_one_per_row(client, monkeypatch):
    statements = []
    original = queries.connect_readonly

    def traced(path=None):
        conn = original(path)
        conn.set_trace_callback(statements.append)
        return conn
    monkeypatch.setattr(queries, "connect_readonly", traced)
    r = client.get("/api/programs?tab=all&limit=200")
    assert r.status_code == 200 and len(r.json()["items"]) == 12
    assert sum("program_changes" in s for s in statements) == 1                         # N+1 이 아니다
    assert len(statements) <= 3


# ---------------------------------------------------------------- /api/programs/{source_id}
def test_unknown_source_id_is_404(client):
    r = client.get("/api/programs/999999")
    assert r.status_code == 404


def test_active_detail_has_extra_fields_and_history(client):
    d = client.get("/api/programs/101").json()
    assert ITEM_FIELDS <= set(d)
    assert (d["summary"], d["target"], d["schedule_text"], d["is_active"]) == ("요약101", "청년", "2026-01-01 ~ 2026-01-02", True)
    assert (d["display_status"], d["d_day"], d["d_day_label"]) == ("모집중", 6, "D-6")
    assert [h["change_type"] for h in d["history"]] == ["extended"]
    assert d["badges"][0]["label"] == "연장"


def test_inactive_row_detail_is_200_without_d_day(client):
    r = client.get("/api/programs/120")
    assert r.status_code == 200
    d = r.json()
    assert d["is_active"] is False
    assert (d["d_day"], d["d_day_label"], d["display_status"], d["group"]) == (None, None, "비활성", "inactive")
    assert d["badges"] == []
    assert [(h["change_type"], h["reason"]) for h in d["history"]] == [("deactivated", "early")]
    assert client.get("/api/programs/121").json()["history"][0]["reason"] == "expired"


def test_history_is_newest_first(client):
    h = client.get("/api/programs/122").json()["history"]
    assert [x["change_type"] for x in h] == ["reactivated", "deactivated"]
    assert h[0]["detected_at"] > h[1]["detected_at"]


def test_expired_active_row_detail_has_no_d_day(client):
    d = client.get("/api/programs/105").json()
    assert (d["is_active"], d["display_status"], d["group"], d["d_day"]) == (True, "마감", "expired", None)


def test_detail_keeps_source_status_for_future_start(client):
    d = client.get("/api/programs/104").json()
    assert (d["display_status"], d["source_status"], d["d_day_label"]) == ("모집예정", "모집중", "시작 D-10")


# ---------------------------------------------------------------- /api/changes
def test_changes_mix_new_and_events_in_descending_time_order(client):
    body = client.get("/api/changes?days=7").json()
    got = [(i["type"], i["source_id"]) for i in body["items"]]
    assert got == [("deactivated", "121"), ("deactivated", "120"), ("reactivated", "122"), ("status_changed", "103"),
                   ("extended", "101"), ("new", "131"), ("new", "130"), ("deactivated", "122")]
    times = [datetime.fromisoformat(i["detected_at"]) for i in body["items"]]
    assert times == sorted(times, reverse=True)
    assert body["total"] == 8 and body["days"] == 7
    assert body["counts"] == {"deactivated": 3, "reactivated": 1, "status_changed": 1, "extended": 1, "new": 2}


def test_changes_items_carry_title_reason_and_values(client):
    items = {(i["type"], i["source_id"]): i for i in client.get("/api/changes").json()["items"]}
    assert items[("deactivated", "121")]["reason"] == "expired"
    assert items[("deactivated", "120")]["reason"] == "early"
    assert items[("deactivated", "122")]["reason"] == "early"
    assert items[("deactivated", "120")]["title"] == "공고120"
    ext = items[("extended", "101")]
    assert (ext["old_value"], ext["new_value"], ext["reason"]) == ("2026-10-05", "2026-10-08", None)
    st = items[("status_changed", "103")]
    assert (st["old_value"], st["new_value"]) == ("모집예정", "모집중")
    new = items[("new", "130")]
    assert (new["title"], new["detected_at"], new["old_value"], new["new_value"], new["reason"]) == \
        ("공고130", "2026-10-02T07:00:00+09:00", None, None, None)


def test_changes_type_filter(client):
    new_only = client.get("/api/changes?type=new").json()
    assert [i["source_id"] for i in new_only["items"]] == ["131", "130"]
    assert new_only["counts"]["deactivated"] == 3                                  # counts 는 type 필터와 무관
    assert len(client.get("/api/changes?type=deactivated").json()["items"]) == 3
    assert client.get("/api/changes?type=nope").status_code == 422


@pytest.fixture
def client_with_old_events(db, tmp_path, monkeypatch):
    path = tmp_path / "with_old.db"
    shutil.copy(db, path)
    c = sqlite3.connect(path)
    for sid, ts in (("106", "2026-09-25T09:00:00+09:00"), ("107", "2026-09-24T23:59:00+09:00")):
        c.execute("INSERT INTO program_changes (source_id, change_type, old_value, new_value, reason, detected_at) "
                  "VALUES (?, 'status_changed', 'a', 'b', NULL, ?)", (sid, ts))
    c.commit()
    c.close()
    monkeypatch.setenv("YOUTH_DB_PATH", str(path))
    app.dependency_overrides[get_today] = lambda: TODAY
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("days, included, excluded", [
    (7, "106", "107"),     # 09-25 은 정확히 7일 전(포함), 09-24 는 8일 전(제외)
    (8, "107", None),      # days=8 이면 둘 다 포함
    (6, None, "106"),      # days=6 이면 09-25 도 제외
])
def test_changes_days_boundary(client_with_old_events, days, included, excluded):
    got = {i["source_id"] for i in client_with_old_events.get(f"/api/changes?days={days}&type=status_changed").json()["items"]}
    if included:
        assert included in got
    if excluded:
        assert excluded not in got


def test_changes_days_bounds(client):
    assert client.get("/api/changes?days=0").status_code == 422
    assert client.get("/api/changes?days=91").status_code == 422


# ---------------------------------------------------------------- /api/meta, /api/health
def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["today"] == "2026-10-02"
    assert m["active_count"] == 13 and m["expired_active_count"] == 1
    assert m["tab_counts"] == {"deadline": 8, "always": 2, "etc": 1, "all": 12}
    assert m["last_collected_at"] == D2.isoformat()                                  # 활성 행의 last_seen_at 최댓값
    assert m["events_7d"] == {"deactivated": 3, "reactivated": 1, "status_changed": 1, "extended": 1}
    assert m["new_7d"] == 2 and m["window_days"] == 7
    assert m["baseline_date"] == "2026-10-01"


def test_last_collected_at_ignores_updated_at_and_detail_fetched_at(client, db):
    """재분류(--reclassify)는 updated_at 만 갱신한다. 그래도 마지막 수집은 last_seen_at 최댓값이다."""
    later = (D2L + timedelta(days=1)).isoformat()
    c = sqlite3.connect(db)
    c.execute("UPDATE programs SET updated_at = ?, detail_fetched_at = ?", (later, later))
    c.commit()
    c.close()
    assert client.get("/api/meta").json()["last_collected_at"] == D2.isoformat()


def test_last_collected_at_ignores_inactive_rows(client, db):
    c = sqlite3.connect(db)
    c.execute("UPDATE programs SET last_seen_at = ? WHERE source_id = '120'", ((D2L + timedelta(days=1)).isoformat(),))   # 120: 비활성
    c.commit()
    c.close()
    assert client.get("/api/meta").json()["last_collected_at"] == D2.isoformat()


def test_last_collected_at_null_when_no_last_seen_at(client, db):
    c = sqlite3.connect(db)
    c.execute("UPDATE programs SET last_seen_at = NULL")
    c.commit()
    c.close()
    assert client.get("/api/meta").json()["last_collected_at"] is None


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "db_available": True}


def test_get_today_defaults_to_seoul_today(monkeypatch):
    monkeypatch.setattr(main, "today_kst", lambda: date(2026, 10, 9))
    assert get_today() == date(2026, 10, 9)


# ---------------------------------------------------------------- 읽기 전용 보장
def all_get_requests(client):
    for url in ("/api/programs?tab=all&limit=200", "/api/programs/101", "/api/programs/120", "/api/changes?days=30",
                "/api/meta", "/api/health"):
        assert client.get(url).status_code == 200


def test_requests_never_change_the_db_file(client, db, tmp_path):
    before = sha(db)
    all_get_requests(client)
    assert sha(db) == before                                                         # 바이트 단위로 그대로
    assert sorted(p.name for p in tmp_path.iterdir()) == ["youth.db"]                # journal 같은 부산물도 없다


def test_api_works_on_a_read_only_file(client, db):
    os.chmod(db, stat.S_IREAD)                                                       # 쓰기를 시도하면 실패하는 파일
    try:
        all_get_requests(client)
    finally:
        os.chmod(db, stat.S_IREAD | stat.S_IWRITE)


def test_there_are_no_write_endpoints(client, db):
    before = sha(db)
    for method in ("post", "put", "patch", "delete"):
        for url in ("/api/programs", "/api/programs/101", "/api/changes", "/api/meta"):
            assert getattr(client, method)(url).status_code == 405
    assert sha(db) == before
    assert {m for r in app.routes if r.path.startswith("/api") for m in r.methods} <= {"GET", "HEAD"}


def test_db_is_opened_with_read_only_uri(client, monkeypatch):
    seen = []
    real_connect = sqlite3.connect

    def spy(database, *a, **k):
        seen.append(database)
        return real_connect(database, *a, **k)
    monkeypatch.setattr(queries.sqlite3, "connect", spy)
    client.get("/api/meta")
    assert seen and all(str(s).startswith("file:") and str(s).endswith("?mode=ro") for s in seen)


# ---------------------------------------------------------------- DB 가 없거나 읽을 수 없을 때: 503 (DB 를 만들지 않는다)
@pytest.mark.parametrize("url", ["/api/programs", "/api/programs/101", "/api/changes", "/api/meta"])
def test_missing_db_returns_503_and_creates_nothing(tmp_path, monkeypatch, url):
    missing = tmp_path / "nope.db"
    monkeypatch.setenv("YOUTH_DB_PATH", str(missing))
    app.dependency_overrides[get_today] = lambda: TODAY
    try:
        r = TestClient(app).get(url)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert not missing.exists() and list(tmp_path.iterdir()) == []


def test_health_reports_missing_db_without_creating_it(tmp_path, monkeypatch):
    missing = tmp_path / "nope.db"
    monkeypatch.setenv("YOUTH_DB_PATH", str(missing))
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db_available": False}
    assert not missing.exists()


def test_file_that_is_not_a_database_returns_503_and_is_untouched(tmp_path, monkeypatch):
    bad = tmp_path / "bad.db"
    bad.write_text("이건 SQLite 파일이 아니다" * 20, encoding="utf-8")
    before = sha(bad)
    monkeypatch.setenv("YOUTH_DB_PATH", str(bad))
    assert TestClient(app).get("/api/meta").status_code == 503
    assert sha(bad) == before


def test_empty_db_without_tables_returns_503_and_is_not_initialized(tmp_path, monkeypatch):
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    monkeypatch.setenv("YOUTH_DB_PATH", str(empty))
    assert TestClient(app).get("/api/programs").status_code == 503
    assert empty.stat().st_size == 0                                                  # 스키마를 만들지 않았다


def test_db_path_defaults_to_backend_data_youth_db(monkeypatch):
    monkeypatch.delenv("YOUTH_DB_PATH", raising=False)
    assert queries.get_db_path() == queries.ROOT / "backend" / "data" / "youth.db"
    monkeypatch.setenv("YOUTH_DB_PATH", "somewhere/else.db")
    assert str(queries.get_db_path()).replace("\\", "/").endswith("somewhere/else.db")


# ---------------------------------------------------------------- CORS
@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_cors_allows_the_dev_frontend_origins(client, origin):
    pre = client.options("/api/programs", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == origin
    assert client.get("/api/health", headers={"Origin": origin}).headers["access-control-allow-origin"] == origin


def test_cors_rejects_other_origins(client):
    pre = client.options("/api/programs", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in pre.headers
    assert "access-control-allow-origin" not in client.get("/api/health", headers={"Origin": "http://evil.example"}).headers
