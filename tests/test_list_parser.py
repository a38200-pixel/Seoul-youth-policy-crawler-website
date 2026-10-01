from pathlib import Path

import pytest

from backend.crawler.list_parser import parse_list, parse_total_count

SAMPLE = Path(__file__).resolve().parent.parent / "backend" / "crawler" / "samples" / "list_sample.html"


@pytest.fixture(scope="module")
def items():
    return parse_list(SAMPLE.read_text(encoding="utf-8"))


def test_item_count(items):
    assert len(items) == 8


def test_first_item(items):
    first = items[0]
    assert first["source_id"] == "74476"
    assert first["category"] == "금융"
    assert first["title"] == "금융위원회 & 서민금융진흥원 <청년미래적금 2차 모집>"
    assert first["status"] == "모집예정"


def test_empty_category_is_none(items):
    second = items[1]
    assert second["source_id"] == "68721"
    assert second["category"] is None
    assert second["status"] == "상시"


def test_ids_are_numeric_and_unique(items):
    ids = [i["source_id"] for i in items]
    assert all(i.isdigit() for i in ids)
    assert len(set(ids)) == len(ids)


def test_all_fields_present(items):
    for item in items:
        assert set(item) == {"source_id", "category", "title", "status"}
        assert item["title"]
        assert item["status"] in {"모집중", "모집예정", "상시", "마감"}


def test_missing_elements_do_not_crash():
    html = '<div class="category-feed"><div class="feed-item"><a class="item-overlay" onclick="goView(\'1\');"></a></div></div>'
    assert parse_list(html) == [{"source_id": "1", "category": None, "title": None, "status": None}]


def test_total_count_skips_sort_tab():
    # 정렬 탭(최신순)도 .tab-st4 .tab-btn li.active a 에 걸리지만 "전체 N건" 을 읽어야 한다
    assert parse_total_count(SAMPLE.read_text(encoding="utf-8")) == 9254


def test_total_count_with_commas_and_missing():
    html = '<div class="tab-st4"><ul class="tab-btn"><li class="active"><a>전체 1,234건</a></li></ul></div>'
    assert parse_total_count(html) == 1234
    assert parse_total_count("<html></html>") is None


def test_empty_page_returns_empty_list():
    assert parse_list("<html><body></body></html>") == []
