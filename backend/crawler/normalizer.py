"""신청기간 문자열 → start_date, end_date. 날짜 기준 시간대는 Asia/Seoul."""
import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

PERIOD_DATED = "dated"
PERIOD_END_ONLY = "end_only"
PERIOD_ALWAYS = "always"
PERIOD_UNKNOWN = "unknown"

_PERIOD_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})")
# 시작일 없이 "~ YYYY-MM-DD" 로 시작하는 형태 (뒤에 시각 등이 붙을 수 있음)
_END_ONLY_RE = re.compile(r"^\s*~\s*(\d{4}-\d{2}-\d{2})")


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


def classify_period(text):
    """신청기간 문자열을 (period_type, start, end) 로 분류한다.

    - 'YYYY-MM-DD ~ YYYY-MM-DD' 가 있으면 ('dated', start, end)
    - 앞에 날짜 없이 '~ YYYY-MM-DD' 로 시작하면 ('end_only', None, end). 날짜가 유효하지 않으면 unknown.
    - 날짜가 없고 "상시"로 시작하면 ('always', None, None)
    - 그 외는 ('unknown', None, None) 이고 경고 로그를 남긴다.
    판정 순서: dated → end_only → always → unknown.
    진행일정 문자열이 아니라 신청기간 문자열만 넘길 것.
    """
    start, end = normalize_period(text)
    if start is not None:
        return PERIOD_DATED, start, end
    m = _END_ONLY_RE.match(text or "")
    if m:
        try:
            return PERIOD_END_ONLY, None, date.fromisoformat(m.group(1))
        except ValueError:
            pass  # 유효하지 않은 날짜 → unknown
    elif (text or "").strip().startswith("상시"):
        return PERIOD_ALWAYS, None, None
    log.warning("신청기간을 분류하지 못함(unknown): %r", text)
    return PERIOD_UNKNOWN, None, None
