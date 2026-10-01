"""상세 페이지 HTML → 상세 필드."""
import logging
import re

from bs4 import BeautifulSoup

from . import selectors as sel

log = logging.getLogger(__name__)


def _clean(text):
    """공백·줄바꿈을 한 칸 공백으로 정리하고, 괄호 안쪽 공백("( 가 )")은 제거한다."""
    text = " ".join(text.split())
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    return text or None


def _text(soup, css):
    el = soup.select_one(css)
    if el is None:
        log.warning("요소 없음: %s", css)
        return None
    return _clean(el.get_text())


def _info_by_label(soup):
    """ul.info li 를 <em> 라벨 기준으로 {라벨: 값} 으로 만든다(순서 무관)."""
    info = {}
    for li in soup.select(sel.DETAIL_INFO_ITEM):
        label_el = li.select_one(sel.DETAIL_INFO_LABEL)
        if label_el is None:
            continue
        label = _clean(label_el.get_text())
        label_el.extract()
        info[label] = _clean(li.get_text())
    return info


def parse_detail(html):
    """상세 HTML에서 필드를 뽑는다. 없는 요소는 None (경고 로그).

    period_text 등은 공백·줄바꿈을 한 칸 공백으로 정리한 원문이다.
    반환 키: category, title, period_text, schedule_text, target, organization, apply_url, summary
    """
    soup = BeautifulSoup(html, "html.parser")
    info = _info_by_label(soup)

    fields = {
        "period_text": sel.LABEL_PERIOD,
        "schedule_text": sel.LABEL_SCHEDULE,
        "target": sel.LABEL_TARGET,
        "organization": sel.LABEL_ORGANIZATION,
    }
    result = {
        "category": _text(soup, sel.DETAIL_CATE),
        "title": _text(soup, sel.DETAIL_TITLE),
    }
    for key, label in fields.items():
        result[key] = info.get(label)
        if label not in info:
            log.warning("라벨 없음: %s", label)
        elif result[key] is None:
            log.warning("값 비어 있음: %s", label)

    apply_el = soup.select_one(sel.DETAIL_APPLY)
    if apply_el is None:
        log.warning("요소 없음: %s", sel.DETAIL_APPLY)
    result["apply_url"] = apply_el.get("href") if apply_el else None

    body = _text(soup, sel.DETAIL_BODY)
    result["summary"] = body[: sel.SUMMARY_MAX_LEN] if body else None
    return result
