from urllib.parse import parse_qs, urlparse

from backend.crawler import selectors as sel

EXPECTED_DEFAULT = (
    "https://youth.seoul.go.kr/infoData/sprtInfo/list.do"
    "?key=2309130006&pageIndex=1&orderBy=regYmd+desc&recordCountPerPage=24"
    "&sc_rcritCurentSitu=%EC%83%81%EC%8B%9C"            # 상시
    "&sc_rcritCurentSitu=%EB%AA%A8%EC%A7%91%EC%A4%91"    # 모집중
    "&sc_rcritCurentSitu=%EB%AA%A8%EC%A7%91%EC%98%88%EC%A0%95"  # 모집예정
)


def test_default_list_url():
    assert sel.list_url() == EXPECTED_DEFAULT


def test_status_param_repeated_with_same_key_in_order():
    q = parse_qs(urlparse(sel.list_url()).query)
    assert q["sc_rcritCurentSitu"] == ["상시", "모집중", "모집예정"]


def test_only_minimal_parameters():
    q = parse_qs(urlparse(sel.list_url()).query, keep_blank_values=True)
    assert set(q) == {"key", "pageIndex", "orderBy", "recordCountPerPage", "sc_rcritCurentSitu"}
    assert "#" not in sel.list_url()


def test_arguments_override_page_order_and_size():
    url = sel.list_url(page=3, order_by="endYmd desc", per_page=8)
    q = parse_qs(urlparse(url).query)
    assert q["pageIndex"] == ["3"]
    assert q["orderBy"] == ["endYmd desc"]
    assert q["recordCountPerPage"] == ["8"]
    assert "orderBy=endYmd+desc" in url
    assert "recordCountPerPage=8" in url


def test_exclude_settings_initial_values():
    assert "68721" in sel.EXCLUDE_IDS
    assert "게시요청 가이드" in sel.EXCLUDE_TITLE_KEYWORDS


def test_detail_url():
    assert sel.detail_url("74445") == (
        "https://youth.seoul.go.kr/infoData/sprtInfo/view.do?sprtInfoId=74445&key=2309130006")
