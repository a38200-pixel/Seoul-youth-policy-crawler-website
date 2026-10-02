from backend.crawler.record import make_row

LIST_ITEM = {"source_id": "74445", "title": "목록 제목", "category": "목록분야", "status": "모집중"}


def test_detail_values_take_priority():
    detail = {"title": "상세 제목", "category": "상세분야", "period_text": "2026-01-01 ~ 2026-01-31",
              "schedule_text": None}
    row = make_row(LIST_ITEM, detail)
    assert row["title"] == "상세 제목"
    assert row["category"] == "상세분야"


def test_falls_back_to_list_values():
    detail = {"title": None, "category": None, "period_text": "상시"}
    row = make_row(LIST_ITEM, detail)
    assert row["title"] == "목록 제목"
    assert row["category"] == "목록분야"


def test_source_status_and_url_come_from_list():
    row = make_row(LIST_ITEM, None)
    assert row["source_status"] == "모집중"
    assert row["source_url"] == "https://youth.seoul.go.kr/infoData/sprtInfo/view.do?sprtInfoId=74445&key=2309130006"


def test_no_detail_means_none_not_unknown():
    row = make_row(LIST_ITEM, None)
    assert row["title"] == "목록 제목"
    for key in ("period_type", "start_date", "end_date", "period_text", "schedule_text",
                "organization", "target", "summary", "apply_url"):
        assert row[key] is None, key


def test_dates_are_isoformat_strings():
    row = make_row(LIST_ITEM, {"period_text": "2026-09-29 ~ 2026-10-09 00 : 00"})
    assert (row["period_type"], row["start_date"], row["end_date"]) == ("dated", "2026-09-29", "2026-10-09")


def test_schedule_text_is_never_classified():
    detail = {"period_text": "상시", "schedule_text": "2026-11-07 ~ 2026-11-08"}
    row = make_row(LIST_ITEM, detail)
    assert row["period_type"] == "always"
    assert row["end_date"] is None
    assert row["schedule_text"] == "2026-11-07 ~ 2026-11-08"


def test_open_keeps_start_date_and_never_uses_schedule_as_end_date():
    detail = {"period_text": "2026-09-20 ~ 00 : 00 [ 선착순 마감 ]", "schedule_text": "2026-10-07 ~ 2026-11-05"}
    row = make_row(LIST_ITEM, detail)
    assert (row["period_type"], row["start_date"], row["end_date"]) == ("open", "2026-09-20", None)
    assert row["schedule_text"] == "2026-10-07 ~ 2026-11-05"


def test_open_without_any_date_has_no_dates():
    row = make_row(LIST_ITEM, {"period_text": "~ 00 : 00 [ 선착순 마감 ]", "schedule_text": "2026-10-07 ~ 2026-11-05"})
    assert (row["period_type"], row["start_date"], row["end_date"]) == ("open", None, None)


def test_detail_without_period_text_is_unknown():
    row = make_row(LIST_ITEM, {"period_text": None})
    assert row["period_type"] == "unknown"
