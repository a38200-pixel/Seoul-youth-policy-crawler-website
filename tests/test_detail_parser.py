from datetime import date
from pathlib import Path

import pytest

from backend.crawler.detail_parser import parse_detail
from backend.crawler.normalizer import classify_period, normalize_period

SAMPLES = Path(__file__).resolve().parent.parent / "backend" / "crawler" / "samples"
SAMPLE = SAMPLES / "detail_sample.html"
SAMPLE_ALWAYS = SAMPLES / "detail_sample_always.html"
SAMPLE_UPCOMING = SAMPLES / "detail_sample_upcoming.html"
SAMPLE_ENDONLY = SAMPLES / "detail_sample_endonly.html"


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


@pytest.fixture(scope="module")
def always():
    return parse_detail(SAMPLE_ALWAYS.read_text(encoding="utf-8"))


def test_always_period(always):
    assert always["period_text"] == "상시 [ 선착순 마감 ]"
    period_type, start, end = classify_period(always["period_text"])
    assert period_type == "always"
    assert start is None and end is None


def test_always_schedule_text_keeps_raw(always):
    assert always["schedule_text"] == "2026-11-07 00:00:00 14시 0분 ~ 15시 30분"


def test_schedule_date_is_not_used_as_end_date(always):
    # 진행일정(2026-11-07)이 신청기간 end_date 로 새어 들어가면 안 된다
    _, start, end = classify_period(always["period_text"])
    assert end is None
    assert normalize_period(always["period_text"]) == (None, None)


def test_dated_sample_period_type(detail):
    assert classify_period(detail["period_text"])[0] == "dated"


@pytest.fixture(scope="module")
def upcoming():
    return parse_detail(SAMPLE_UPCOMING.read_text(encoding="utf-8"))


# 아래 기대값은 detail_sample_upcoming.html 을 직접 읽고 정한 값이다(파서 출력 복사 아님).
# 대상 <li> 는 HTML 에서 비어 있으므로 None.
def test_upcoming_category_and_title(upcoming):
    assert upcoming["category"] == "금융"
    assert upcoming["title"] == "금융위원회 & 서민금융진흥원 <청년미래적금 2차 모집>"


def test_upcoming_period_text_is_raw(upcoming):
    assert upcoming["period_text"] == "2026-10-07 ~ 2026-10-16 00 : 00"


def test_upcoming_target_empty_is_none(upcoming):
    assert upcoming["target"] is None


def test_upcoming_organization(upcoming):
    # HTML 원문은 "(금융위원회 )" 이고 괄호 안쪽 공백은 정리 규칙으로 제거된다
    assert upcoming["organization"] == "기타 (금융위원회)"


def test_upcoming_schedule_text(upcoming):
    assert upcoming["schedule_text"] == "2026-10-07 ~ 2026-10-16 0시 0분 ~ 0시 0분"


def test_upcoming_classify_period(upcoming):
    assert classify_period(upcoming["period_text"]) == ("dated", date(2026, 10, 7), date(2026, 10, 16))


def test_warning_distinguishes_missing_label_from_empty_value(caplog):
    # 선택 필드(대상·담당기관)는 DEBUG 로 내려갔지만, 두 경우의 메시지는 여전히 구분된다
    html = """
    <div class="cont"><em class="cate">금융</em><div class="tit"><strong>제목</strong></div>
    <ul class="info">
      <li><em>신청기간</em> 2026-01-01 ~ 2026-01-31</li>
      <li><em>대상</em> </li>
    </ul></div>
    """
    with caplog.at_level("DEBUG"):
        d = parse_detail(html)
    # 반환값은 둘 다 None
    assert d["target"] is None
    assert d["organization"] is None
    assert "값 비어 있음: 대상" in caplog.text
    assert "라벨 없음: 대상" not in caplog.text
    assert "라벨 없음: 담당기관" in caplog.text
    assert "값 비어 있음: 담당기관" not in caplog.text


def _levels(caplog, text):
    return {r.levelname for r in caplog.records if text in r.getMessage()}


def test_optional_fields_log_at_debug_not_warning(caplog):
    html = """
    <div class="cont"><em class="cate">금융</em><div class="tit"><strong>제목</strong></div>
    <ul class="info">
      <li><em>신청기간</em> 2026-01-01 ~ 2026-01-31</li>
      <li><em>대상</em> </li>
    </ul></div>
    """
    with caplog.at_level("DEBUG"):
        parse_detail(html)
    assert _levels(caplog, "값 비어 있음: 대상") == {"DEBUG"}
    assert _levels(caplog, "라벨 없음: 담당기관") == {"DEBUG"}
    assert _levels(caplog, "라벨 없음: 진행일정") == {"DEBUG"}
    # 라벨 관련 메시지는 WARNING 이 하나도 없어야 한다 (버튼·본문 요소 없음 경고는 이 테스트의 대상이 아니다)
    label_warnings = [r for r in caplog.records if r.levelname == "WARNING"
                      and r.getMessage().startswith(("라벨 없음", "값 비어 있음"))]
    assert label_warnings == []


def test_required_period_field_logs_warning(caplog):
    missing = '<div class="cont"><div class="tit"><strong>제목</strong></div><ul class="info"><li><em>대상</em> 청년</li></ul></div>'
    empty = '<div class="cont"><div class="tit"><strong>제목</strong></div><ul class="info"><li><em>신청기간</em> </li></ul></div>'
    with caplog.at_level("DEBUG"):
        parse_detail(missing)
    assert _levels(caplog, "라벨 없음: 신청기간") == {"WARNING"}
    caplog.clear()
    with caplog.at_level("DEBUG"):
        parse_detail(empty)
    assert _levels(caplog, "값 비어 있음: 신청기간") == {"WARNING"}


# 아래 기대값은 detail_sample_endonly.html(74531)을 직접 읽고 정했다: 신청기간 "~ 2026-10-08 00 : 00", 대상 <li> 는 빈 값.
@pytest.fixture(scope="module")
def endonly():
    return parse_detail(SAMPLE_ENDONLY.read_text(encoding="utf-8"))


def test_endonly_sample_fields(endonly):
    assert endonly["title"] == "서울청년센터 영등포 <2026 제3회 여민락 문화교류축제 「인사 in Seoul」"
    assert endonly["category"] == "대외활동"
    assert endonly["period_text"] == "~ 2026-10-08 00 : 00"
    assert endonly["schedule_text"] == "2026-10-09 00:00:00 0시 0분 ~ 0시 0분"
    assert endonly["target"] is None


def test_endonly_sample_classified_as_end_only(endonly):
    assert classify_period(endonly["period_text"]) == ("end_only", None, date(2026, 10, 8))


def test_endonly_sample_has_no_sensitive_strings():
    text = SAMPLE_ENDONLY.read_text(encoding="utf-8")
    assert "weblog2" not in text and "pc_id" not in text


def test_parentheses_inner_spaces_removed():
    html = '<div class="cont"><ul class="info"><li><em>담당기관</em> 기타 ( 금융위원회 )</li></ul></div>'
    assert parse_detail(html)["organization"] == "기타 (금융위원회)"


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
