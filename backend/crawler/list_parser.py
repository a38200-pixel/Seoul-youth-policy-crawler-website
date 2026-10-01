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


_TOTAL_RE = re.compile(r"전체\s*([\d,]+)건")


def parse_total_count(html):
    """목록 페이지의 "전체 N건" 에서 N 을 정수로 반환. 못 찾으면 None(경고 로그).

    실제 구조: `.tab-st4` 가 페이지에 두 군데 있다.
      1) 정렬 탭   `<li class="active"><a>최신순</a></li>`   (+ 마감순)
      2) 건수 탭   `<li class="active"><a>전체 9254건</a></li>` (+ 상시지원 N건, 일반지원 N건)
    `.tab-st4 .tab-btn li.active a` 는 두 탭의 active 링크에 모두 걸리므로(문서 순서상 첫 번째는 "최신순"),
    텍스트가 '전체 N건' 형태인 것만 쓴다.
    """
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select(sel.LIST_TOTAL):
        m = _TOTAL_RE.search(el.get_text())
        if m:
            return int(m.group(1).replace(",", ""))
    log.warning("전체 건수를 찾지 못함: %s", sel.LIST_TOTAL)
    return None


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
