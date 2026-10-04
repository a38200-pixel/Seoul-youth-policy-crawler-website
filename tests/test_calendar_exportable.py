"""display.calendar_exportable 판정 테스트(순수 함수). 네트워크·DB 없음."""
from datetime import date

import pytest

from backend.service.display import calendar_exportable, compute_display

TODAY = date(2026, 10, 4)


def prow(**over):
    base = {"source_id": "1", "period_type": "dated", "start_date": "2026-09-20", "end_date": "2026-10-10",
            "source_status": "모집중", "category": "금융", "is_active": 1}
    base.update(over)
    return base


@pytest.mark.parametrize("over, expected", [
    ({}, True),                                                                              # 모집중, 마감일 미래
    ({"end_date": "2026-10-04"}, True),                                                       # 마감일이 오늘이면 포함
    ({"end_date": "2026-10-03"}, False),                                                      # 어제 마감 = 만료
    ({"start_date": "2026-10-20", "end_date": "2026-10-30"}, True),                           # 모집예정(dated)
    ({"period_type": "end_only", "start_date": None, "end_date": "2026-10-10"}, True),
    ({"period_type": "open", "start_date": "2026-10-20", "end_date": None}, False),           # 모집예정으로 보이지만 마감일이 없다
    ({"period_type": "open", "start_date": None, "end_date": None}, False),                   # 마감일 미정
    ({"period_type": "always", "start_date": None, "end_date": None}, False),                 # 상시
    ({"period_type": "unknown", "start_date": None, "end_date": None}, False),
    ({"period_type": None, "start_date": None, "end_date": None}, False),                     # 상세 미수신
    ({"is_active": 0}, False),                                                                # 비활성
    ({"end_date": "2026-10-10T18:00:00+09:00"}, True),                                        # 시각이 붙어 있어도 날짜만 본다
])
def test_calendar_exportable_rule(over, expected):
    row = prow(**over)
    assert calendar_exportable(row, compute_display(row, TODAY), TODAY) is expected
