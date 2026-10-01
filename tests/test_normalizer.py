from datetime import date

from backend.crawler.normalizer import classify_period, normalize_period, today_kst


def test_period_with_newline_and_time():
    text = "2026-09-29 ~ 2026-10-09\n 00 : 00"
    assert normalize_period(text) == (date(2026, 9, 29), date(2026, 10, 9))


def test_period_without_spaces_around_tilde():
    assert normalize_period("2026-01-01~2026-01-31") == (date(2026, 1, 1), date(2026, 1, 31))


def test_no_date_returns_none():
    assert normalize_period("상시") == (None, None)
    assert normalize_period("") == (None, None)
    assert normalize_period(None) == (None, None)


def test_single_date_is_not_a_period():
    assert normalize_period("2026-09-29") == (None, None)


def test_invalid_date_returns_none():
    assert normalize_period("2026-13-45 ~ 2026-14-01") == (None, None)


def test_classify_dated():
    assert classify_period("2026-09-29 ~ 2026-10-09\n 00 : 00") == ("dated", date(2026, 9, 29), date(2026, 10, 9))


def test_classify_always():
    assert classify_period("상시 [ 선착순 마감 ]") == ("always", None, None)
    assert classify_period("  상시") == ("always", None, None)


def test_classify_unknown_logs_warning(caplog):
    for text in ["추후 공지", "", None, "2026-13-45 ~ 2026-14-01"]:
        caplog.clear()
        assert classify_period(text) == ("unknown", None, None)
        assert "unknown" in caplog.text


def test_classify_end_only_with_time():
    assert classify_period("~ 2026-10-08 00 : 00") == ("end_only", None, date(2026, 10, 8))


def test_classify_end_only_variants():
    assert classify_period("~2026-10-08") == ("end_only", None, date(2026, 10, 8))
    assert classify_period("  ~  2026-10-08\n 00 : 00") == ("end_only", None, date(2026, 10, 8))


def test_classify_end_only_invalid_date_is_unknown(caplog):
    assert classify_period("~ 2026-13-45 00 : 00") == ("unknown", None, None)
    assert "unknown" in caplog.text


def test_classify_tilde_without_date_is_unknown():
    assert classify_period("~") == ("unknown", None, None)
    assert classify_period("~ 추후 공지") == ("unknown", None, None)


def test_classify_order_dated_before_end_only_before_always():
    assert classify_period("2026-01-01 ~ 2026-01-31")[0] == "dated"
    assert classify_period("~ 2026-01-31")[0] == "end_only"
    assert classify_period("상시 [ 선착순 마감 ]")[0] == "always"
    # 날짜 앞에 다른 글자가 있는 '~' 는 end_only 가 아니다
    assert classify_period("마감 ~ 2026-01-31")[0] == "unknown"


def test_classify_always_prefix_with_dates_returns_dates():
    assert classify_period("상시 2026-01-01 ~ 2026-01-31") == ("dated", date(2026, 1, 1), date(2026, 1, 31))


def test_today_kst_is_date():
    assert isinstance(today_kst(), date)
