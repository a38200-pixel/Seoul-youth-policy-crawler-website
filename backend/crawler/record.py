"""목록 항목 + 상세 파싱 결과 → DB 한 행(dict)."""
from . import selectors as sel
from .normalizer import classify_period

# 상세 페이지에서만 얻는 필드 (detail 이 None 이면 전부 None)
DETAIL_FIELDS = (
    "organization", "target", "summary", "period_text", "schedule_text", "apply_url",
)


def _iso(d):
    return d.isoformat() if d is not None else None


def make_row(list_item, detail):
    """DB 한 행을 만든다. 날짜는 isoformat() 문자열로 둔다.

    list_item: source_id, title, category, status(목록의 모집상태)
    detail: parse_detail 결과 또는 None(상세를 받지 않음)
    - title/category 는 상세 값을 우선하고 없으면 목록 값을 쓴다.
    - period_type/start_date/end_date 는 신청기간(period_text)으로만 만든다. schedule_text 는 쓰지 않는다.
    - detail 이 None 이면 상세 필드와 period_type 은 None 이다('unknown' 아님).
    """
    source_id = list_item["source_id"]
    d = detail or {}
    row = {
        "source_id": source_id,
        "title": d.get("title") or list_item.get("title"),
        "category": d.get("category") or list_item.get("category"),
        "source_status": list_item.get("status"),
        "source_url": sel.detail_url(source_id),
        "period_type": None,
        "start_date": None,
        "end_date": None,
    }
    for field in DETAIL_FIELDS:
        row[field] = d.get(field)

    if detail is not None:
        period_type, start, end = classify_period(detail.get("period_text"))
        row["period_type"] = period_type
        row["start_date"] = _iso(start)
        row["end_date"] = _iso(end)
    return row
