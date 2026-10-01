"""신청기간 문자열 → start_date, end_date. 날짜 기준 시간대는 Asia/Seoul."""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

_PERIOD_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})")


def today_kst():
    return datetime.now(KST).date()


def normalize_period(text):
    """'YYYY-MM-DD ~ YYYY-MM-DD' 를 찾아 (start, end) date 로 반환.

    날짜를 못 찾거나 유효하지 않은 날짜면 (None, None). 원문은 호출하는 쪽이 period_text 에 보관한다.
    """
    m = _PERIOD_RE.search(text or "")
    if not m:
        return None, None
    try:
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    except ValueError:
        return None, None
