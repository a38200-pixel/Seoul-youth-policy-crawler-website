"""목록 페이지 HTML → 공고 기본정보."""
import logging
import re

from bs4 import BeautifulSoup

from . import selectors as sel

log = logging.getLogger(__name__)

_GO_VIEW_RE = re.compile(r"goView\('(\d+)'\)")


def _text(parent, css):
    el = parent.select_one(css)
    if el is None:
        log.warning("요소 없음: %s", css)
        return None
    return " ".join(el.get_text().split()) or None


def parse_list(html):
    """목록 HTML에서 공고 리스트를 뽑는다. 항목마다 하위 요소를 따로 찾는다.

    반환: [{"source_id", "category", "title", "status"}, ...]
    공고 ID를 못 찾은 항목은 건너뛴다. 분야는 비어 있으면 None.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select(sel.LIST_ITEM):
        overlay = item.select_one(sel.LIST_OVERLAY)
        m = _GO_VIEW_RE.search(overlay.get("onclick", "")) if overlay else None
        if not m:
            log.warning("공고 ID를 찾지 못해 건너뜀: %s", sel.LIST_OVERLAY)
            continue
        results.append({
            "source_id": m.group(1),
            "category": _text(item, sel.LIST_CATE),
            "title": _text(item, sel.LIST_NAME),
            "status": _text(item, sel.LIST_STATE),
        })
    return results
