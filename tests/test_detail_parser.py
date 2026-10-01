from pathlib import Path

import pytest

from backend.crawler.detail_parser import parse_detail
from backend.crawler.normalizer import normalize_period

SAMPLE = Path(__file__).resolve().parent.parent / "backend" / "crawler" / "samples" / "detail_sample.html"


@pytest.fixture(scope="module")
def detail():
    return parse_detail(SAMPLE.read_text(encoding="utf-8"))


def test_category_and_title(detail):
    assert detail["category"] == "마음건강"
    assert detail["title"] == "서울신용보증재단 성북종합지원센터 <성북동길, 마음환기산책>"


def test_labeled_fields(detail):
    assert detail["period_text"].startswith("2026-09-29 ~ 2026-10-09")
    assert detail["target"] == "제한없음"
    assert detail["organization"] == "기타 (서울신용보증재단 성북종합지원센터)"
    assert "2026-10-10" in detail["schedule_text"]


def test_period_text_feeds_normalizer(detail):
    start, end = normalize_period(detail["period_text"])
    assert (str(start), str(end)) == ("2026-09-29", "2026-10-09")


def test_apply_url(detail):
    assert detail["apply_url"] == "https://forms.gle/2vnKjTDuFRBndSmWA"


def test_summary_limited_to_200(detail):
    assert 0 < len(detail["summary"]) <= 200
    assert "마음 환기 산책" in detail["summary"]


def test_label_order_does_not_matter():
    html = """
    <div class="cont"><em class="cate">금융</em><div class="tit"><strong>제목</strong></div>
    <ul class="info">
      <li><em>담당기관</em> 서울시</li>
      <li><em>대상</em> 청년</li>
      <li><em>신청기간</em> 2026-01-01 ~ 2026-01-31</li>
    </ul></div>
    """
    d = parse_detail(html)
    assert d["organization"] == "서울시"
    assert d["target"] == "청년"
    assert d["period_text"] == "2026-01-01 ~ 2026-01-31"
    assert d["schedule_text"] is None


def test_missing_elements_do_not_crash():
    d = parse_detail("<html><body></body></html>")
    assert all(v is None for v in d.values())
