"""표시 규칙(backend/service/display.py) 테스트. today=2026-10-02 고정, DB·네트워크 없음."""
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.crawler.db import init_db
from backend.crawler.normalizer import classify_period
from backend.service import display
from backend.service.display import badges, compute_display, sort_programs, visible_by_default

TODAY = date(2026, 10, 2)
KST = timezone(timedelta(hours=9))


def row(ptype, start=None, end=None, status="모집중", category="금융", sid="1", **extra):
    return {"source_id": sid, "period_type": ptype, "start_date": start, "end_date": end,
            "source_status": status, "category": category, **extra}


def show(r):
    return compute_display(r, TODAY)


# ---------------------------------------------------------------- dated / end_only: D-Day, 마감
def test_end_today_is_d_day():
    d = show(row("dated", "2026-09-20", "2026-10-02"))
    assert (d["display_status"], d["d_day"], d["d_day_label"], d["group"]) == ("모집중", 0, "D-Day", "recruiting")


def test_end_tomorrow_is_d_minus_1():
    d = show(row("dated", "2026-09-20", "2026-10-03"))
    assert (d["display_status"], d["d_day"], d["d_day_label"]) == ("모집중", 1, "D-1")


def test_end_yesterday_is_expired_and_excluded_from_sort_key():
    d = show(row("dated", "2026-09-20", "2026-10-01"))
    assert d["group"] == "expired" and d["display_status"] == "마감"
    assert d["d_day"] is None and d["d_day_label"] is None and d["sort_key"] is None
    assert not visible_by_default(d)


def test_start_today_is_already_recruiting():
    d = show(row("dated", "2026-10-02", "2026-10-05"))
    assert (d["display_status"], d["d_day_label"]) == ("모집중", "D-3")


def test_one_day_recruitment_on_today_is_d_day():
    assert show(row("dated", "2026-10-02", "2026-10-02"))["d_day_label"] == "D-Day"


def test_end_only_uses_end_date_only():
    d = show(row("end_only", None, "2026-10-08"))
    assert (d["display_status"], d["d_day"], d["d_day_label"], d["group"]) == ("모집중", 6, "D-6", "recruiting")
    assert show(row("end_only", None, "2026-10-01"))["group"] == "expired"


# ---------------------------------------------------------------- 시작일이 미래 → 모집예정(날짜 우선)
def test_future_start_is_upcoming_even_if_site_says_recruiting_and_status_is_preserved():
    d = show(row("dated", "2026-10-12", "2026-10-21", status="모집중"))
    assert (d["display_status"], d["d_day"], d["d_day_label"], d["group"]) == ("모집예정", 10, "시작 D-10", "upcoming")
    assert d["source_status"] == "모집중"                       # 사이트 상태는 그대로 같이 담는다


def test_site_upcoming_status_is_preserved_too():
    d = show(row("dated", "2026-10-03", "2026-10-09", status="모집예정"))
    assert (d["d_day_label"], d["source_status"]) == ("시작 D-1", "모집예정")


def test_result_has_exactly_the_documented_keys():
    assert set(show(row("dated", "2026-09-20", "2026-10-09"))) == {
        "display_status", "d_day", "d_day_label", "group", "sort_key", "source_status"}


# ---------------------------------------------------------------- open
def test_open_with_past_start_is_deadline_undecided():
    d = show(row("open", "2026-09-20", None))
    assert (d["display_status"], d["d_day"], d["d_day_label"], d["group"]) == ("마감일 미정", None, None, "open")


def test_open_without_any_date_is_deadline_undecided():
    assert show(row("open", None, None))["display_status"] == "마감일 미정"


def test_open_starting_today_is_deadline_undecided():
    assert show(row("open", "2026-10-02", None))["group"] == "open"


def test_open_with_future_start_is_upcoming():
    d = show(row("open", "2026-10-10", None, status="모집중"))
    assert (d["display_status"], d["d_day"], d["d_day_label"], d["group"]) == ("모집예정", 8, "시작 D-8", "upcoming")
    assert d["source_status"] == "모집중"


# ---------------------------------------------------------------- always / unknown
def test_always_with_category_is_always_group():
    d = show(row("always", category="금융", status="상시"))
    assert (d["display_status"], d["d_day"], d["d_day_label"], d["group"]) == ("상시", None, None, "always")
    assert visible_by_default(d)


@pytest.mark.parametrize("category", [None, "", "   "])
def test_always_without_category_is_always_etc_and_hidden_by_default(category):
    d = show(row("always", category=category, status="상시"))
    assert (d["display_status"], d["group"]) == ("상시", "always_etc")
    assert not visible_by_default(d)


def test_unknown_needs_confirmation():
    d = show(row("unknown"))
    assert (d["display_status"], d["d_day"], d["group"]) == ("확인 필요", None, "unknown")
    assert visible_by_default(d)


def test_row_without_detail_is_treated_as_unknown():
    assert show(row(None))["group"] == "unknown"


def test_dated_without_end_date_falls_back_to_unknown():
    assert show(row("dated", "2026-09-20", None))["group"] == "unknown"


# ---------------------------------------------------------------- 날짜만 사용(시각·진행일정 무시)
def test_period_text_with_time_uses_date_only():
    ptype, start, end = classify_period("~ 2026-10-06 18 : 00")                    # end_only, 시각이 붙은 원문
    d = show(row(ptype, start and start.isoformat(), end.isoformat()))
    assert (ptype, d["d_day"], d["d_day_label"]) == ("end_only", 4, "D-4")


def test_time_inside_date_columns_is_ignored():
    d = show(row("dated", "2026-09-20T23:59:00+09:00", "2026-10-02 23:59"))         # 늦은 시각이어도 오늘 마감은 D-Day
    assert (d["d_day_label"], d["group"]) == ("D-Day", "recruiting")


def test_accepts_date_and_datetime_objects():
    d = show(row("dated", date(2026, 9, 20), datetime(2026, 10, 5, 23, 0, tzinfo=KST)))
    assert d["d_day_label"] == "D-3"


def test_schedule_text_is_never_used():
    d = show(row("dated", "2026-09-20", "2026-10-10", schedule_text="2026-01-01 ~ 2026-01-02"))
    assert (d["d_day"], d["group"]) == (8, "recruiting")                             # 진행일정이 과거여도 영향 없음
    assert not any("schedule" in k for k in d)
    a = show(row("always", schedule_text="2026-01-01 ~ 2026-01-02", status="상시"))
    assert a["group"] == "always"


def test_today_defaults_to_seoul_today(monkeypatch):
    monkeypatch.setattr(display, "today_kst", lambda: date(2026, 10, 2))
    assert compute_display(row("dated", "2026-09-20", "2026-10-03"))["d_day_label"] == "D-1"
    monkeypatch.setattr(display, "today_kst", lambda: date(2026, 10, 4))
    assert compute_display(row("dated", "2026-09-20", "2026-10-03"))["group"] == "expired"


def test_accepts_sqlite_rows():
    conn = init_db(":memory:")
    conn.execute("INSERT INTO programs (source_id, period_type, start_date, end_date, source_status, category) "
                 "VALUES ('7', 'dated', '2026-09-20', '2026-10-05', '모집중', '금융')")
    r = conn.execute("SELECT * FROM programs").fetchone()
    assert compute_display(r, TODAY)["d_day_label"] == "D-3"
    conn.close()


# ---------------------------------------------------------------- 정렬
def mixed_rows():
    return [
        row("dated", "2026-09-20", "2026-10-05", sid="20"),                      # D-3
        row("dated", "2026-09-20", "2026-10-02", sid="30"),                      # D-Day
        row("dated", "2026-09-20", "2026-10-05", sid="9"),                       # D-3, 동률(source_id 숫자순으로 20 보다 앞)
        row("end_only", None, "2026-10-04", sid="40"),                           # D-2
        row("dated", "2026-10-12", "2026-10-21", sid="50"),                      # 모집예정(시작 10-12)
        row("open", "2026-10-05", None, sid="51"),                               # 시작이 미래인 open → 모집예정(시작 10-05)
        row("open", "2026-09-20", None, sid="60"),
        row("open", None, None, sid="61"),
        row("open", "2026-09-10", None, sid="62"),
        row("always", category="금융", sid="70", status="상시"),
        row("always", category="교육", sid="71", status="상시"),
        row("always", category=None, sid="80", status="상시"),
        row("unknown", sid="90"),
        row(None, sid="91"),
        row("dated", "2026-09-20", "2026-10-01", sid="99"),                      # 마감 지남 → 제외
    ]


def test_sort_order_across_groups():
    rows = list(reversed(mixed_rows()))                                          # 입력 순서와 무관해야 한다
    out = sort_programs(rows, TODAY)
    assert [r["source_id"] for r, _ in out] == [
        "30", "40", "9", "20",        # 모집중: D-Day, D-2, D-3(동률: source_id 9 < 20)
        "51", "50",                   # 모집예정: 시작일 오름차순(10-05, 10-12)
        "62", "60", "61",             # 마감일 미정: 시작일 오름차순(없으면 뒤)
        "71", "70",                   # 상시(분야순)
        "80",                         # 상시-기타
        "90", "91",                   # 확인 필요
    ]
    assert [d["group"] for _, d in out] == (["recruiting"] * 4 + ["upcoming"] * 2 + ["open"] * 3 +
                                             ["always"] * 2 + ["always_etc"] + ["unknown"] * 2)


def test_expired_rows_are_excluded_from_sorting():
    out = sort_programs(mixed_rows(), TODAY)
    assert "99" not in [r["source_id"] for r, _ in out]
    assert all(d["group"] != "expired" for _, d in out)


def test_groups_follow_the_documented_order_constant():
    assert display.GROUP_ORDER == ("recruiting", "upcoming", "open", "always", "always_etc", "unknown")
    ranks = [sort_programs([r], TODAY)[0][1]["sort_key"][0] for r in
             (row("dated", "2026-09-20", "2026-10-05"), row("dated", "2026-10-12", "2026-10-21"), row("open", "2026-09-20"),
              row("always", category="금융"), row("always", category=None), row("unknown"))]
    assert ranks == sorted(ranks) and len(set(ranks)) == 6


def test_d_day_ties_break_by_end_date_then_source_id():
    # 같은 d_day 면 end_date 도 같으므로 결국 source_id(숫자 순서)로 결정된다
    rows = [row("dated", "2026-09-20", "2026-10-06", sid=s) for s in ("100", "21", "3")]
    assert [r["source_id"] for r, _ in sort_programs(rows, TODAY)] == ["3", "21", "100"]


def test_non_numeric_source_ids_sort_after_numeric_ones():
    rows = [row("unknown", sid="abc"), row("unknown", sid="12"), row("unknown", sid="3")]
    assert [r["source_id"] for r, _ in sort_programs(rows, TODAY)] == ["3", "12", "abc"]


def test_hidden_by_default_groups():
    assert display.HIDDEN_BY_DEFAULT == {"expired", "always_etc"}
    assert [visible_by_default(d) for _, d in sort_programs(mixed_rows(), TODAY)].count(False) == 1   # always_etc 한 건


# ---------------------------------------------------------------- 배지
def ev(eid, ctype, old, new, detected):
    return {"id": eid, "change_type": ctype, "old_value": old, "new_value": new, "detected_at": detected}


OLD_ROW = "2026-09-01T09:00:00+09:00"      # NEW 가 아닌(기준일 이전) first_seen_at


def test_new_badge_baseline_day_is_not_new():
    assert badges("2026-10-01T22:10:00+09:00", [], TODAY) == []                  # 기준일에 처음 본 행은 NEW 가 아니다
    (b,) = badges("2026-10-02T07:00:00+09:00", [], TODAY)
    assert (b["type"], b["label"], b["detail"]) == ("new", "NEW", None)


def test_new_badge_window_boundary_7_and_8_days():
    first = "2026-10-02T07:00:00+09:00"
    assert [b["type"] for b in badges(first, [], date(2026, 10, 9))] == ["new"]   # 정확히 7일 차이
    assert badges(first, [], date(2026, 10, 10)) == []                            # 8일 차이


def test_event_badge_window_boundary_7_and_8_days():
    e = [ev(1, "extended", "2026-10-08", "2026-10-15", "2026-10-02T09:00:00+09:00")]
    assert [b["type"] for b in badges(OLD_ROW, e, date(2026, 10, 9))] == ["extended"]   # 7일 차이는 포함
    assert badges(OLD_ROW, e, date(2026, 10, 10)) == []                                 # 8일 차이는 제외


def test_only_the_latest_event_per_type_is_used():
    events = [
        ev(1, "extended", "2026-10-08", "2026-10-10", "2026-10-05T09:00:00+09:00"),
        ev(2, "extended", "2026-10-10", "2026-10-15", "2026-10-07T09:00:00+09:00"),   # 가장 최근
        ev(3, "extended", "2026-10-01", "2026-10-08", "2026-10-03T09:00:00+09:00"),
    ]
    for ordered in (events, list(reversed(events))):                              # 입력 순서와 무관
        (b,) = badges(OLD_ROW, ordered, date(2026, 10, 8))
        assert (b["type"], b["label"], b["detail"]) == ("extended", "연장", "2026-10-10 → 2026-10-15")


def test_same_timestamp_uses_the_larger_event_id():
    t = "2026-10-05T09:00:00+09:00"
    (b,) = badges(OLD_ROW, [ev(5, "status_changed", "a", "b", t), ev(9, "status_changed", "b", "c", t)], date(2026, 10, 6))
    assert b["detail"] == "b → c"


def test_each_kind_has_its_own_latest_badge_in_fixed_order():
    events = [
        ev(1, "status_changed", "모집예정", "모집중", "2026-10-06T09:00:00+09:00"),
        ev(2, "period_changed",
           '{"period_type": "open", "start_date": "2026-09-20", "end_date": null}',
           '{"period_type": "dated", "start_date": "2026-09-20", "end_date": "2026-10-20"}', "2026-10-06T09:00:00+09:00"),
        ev(3, "shortened", "2026-10-15", "2026-10-08", "2026-10-06T09:00:00+09:00"),
        ev(4, "extended", "2026-10-08", "2026-10-15", "2026-10-06T09:00:00+09:00"),
    ]
    got = badges("2026-10-02T07:00:00+09:00", events, date(2026, 10, 7))
    assert [(b["type"], b["label"]) for b in got] == [
        ("new", "NEW"), ("extended", "연장"), ("shortened", "단축"), ("period_changed", "기간 변경"), ("status_changed", "상태 변경")]
    detail = {b["type"]: b["detail"] for b in got}
    assert detail["extended"] == "2026-10-08 → 2026-10-15"
    assert detail["shortened"] == "2026-10-15 → 2026-10-08"
    assert detail["status_changed"] == "모집예정 → 모집중"
    assert detail["period_changed"] == "open 2026-09-20 ~ - → dated 2026-09-20 ~ 2026-10-20"


def test_deactivated_is_not_a_badge_but_reactivated_is():
    events = [ev(1, "deactivated", "1", "0", "2026-10-05T09:00:00+09:00"),
              ev(2, "reactivated", "0", "1", "2026-10-06T09:00:00+09:00")]
    (b,) = badges(OLD_ROW, events, date(2026, 10, 7))
    assert (b["type"], b["label"], b["detail"]) == ("reactivated", "재등록", None)
    assert badges(OLD_ROW, [events[0]], date(2026, 10, 7)) == []


def test_events_outside_the_window_are_ignored_and_none_events_are_ok():
    old = [ev(1, "status_changed", "a", "b", "2026-09-20T09:00:00+09:00")]
    assert badges(OLD_ROW, old, TODAY) == []
    assert badges(OLD_ROW, None, TODAY) == []
    assert badges(None, [], TODAY) == []


def test_custom_window_days():
    e = [ev(1, "extended", "x", "y", "2026-10-02T09:00:00+09:00")]
    assert badges(OLD_ROW, e, date(2026, 10, 5), window_days=3)[0]["type"] == "extended"
    assert badges(OLD_ROW, e, date(2026, 10, 6), window_days=3) == []


def test_event_dates_are_compared_in_seoul_time():
    # 2026-10-01T16:30Z = 2026-10-02 01:30 KST → 오늘이 10-09 이면 7일 차이로 포함
    e = [ev(1, "extended", "x", "y", "2026-10-01T16:30:00+00:00")]
    assert [b["type"] for b in badges(OLD_ROW, e, date(2026, 10, 9))] == ["extended"]
    assert badges(OLD_ROW, e, date(2026, 10, 10)) == []


def test_badges_accept_sqlite_rows_from_program_changes():
    conn = init_db(":memory:")
    conn.execute("INSERT INTO program_changes (source_id, change_type, old_value, new_value, reason, detected_at) "
                 "VALUES ('1', 'extended', '2026-10-08', '2026-10-15', NULL, '2026-10-05T09:00:00+09:00')")
    events = conn.execute("SELECT * FROM program_changes").fetchall()
    (b,) = badges(OLD_ROW, events, date(2026, 10, 6))
    assert b["detail"] == "2026-10-08 → 2026-10-15"
    conn.close()


def test_badges_default_today_is_seoul_today(monkeypatch):
    monkeypatch.setattr(display, "today_kst", lambda: date(2026, 10, 9))
    assert [b["type"] for b in badges("2026-10-02T07:00:00+09:00", [])] == ["new"]
    monkeypatch.setattr(display, "today_kst", lambda: date(2026, 10, 10))
    assert badges("2026-10-02T07:00:00+09:00", []) == []
