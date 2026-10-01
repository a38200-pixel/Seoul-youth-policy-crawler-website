"""사이트 URL과 CSS 셀렉터 상수. 셀렉터는 이 파일에만 둔다."""
from urllib.parse import urlencode

KEY = "2309130006"
BASE_URL = "https://youth.seoul.go.kr/infoData/sprtInfo"
LIST_URL = f"{BASE_URL}/list.do"
DETAIL_URL = f"{BASE_URL}/view.do"

# 수집 대상 모집상태 (마감 제외)
TARGET_STATUSES = ["모집중", "모집예정", "상시"]
# 목록 URL 의 sc_rcritCurentSitu 로 보내는 값과 순서(사용자가 주소창에서 확인한 순서)
LIST_STATUS_PARAMS = ["상시", "모집중", "모집예정"]

# 수집에서 제외할 공고 (안내·가이드성 게시물)
EXCLUDE_IDS = {"68721"}
EXCLUDE_TITLE_KEYWORDS = ["게시요청 가이드"]

# 목록 페이지
LIST_FEED = ".category-feed"
# "전체 N건" 탭. .tab-st4 가 두 군데(정렬 탭, 건수 탭)에 있어 이 선택자는 둘 다 잡는다.
# 텍스트가 정규식 r"전체\s*([\d,]+)건" 에 맞는 것만 쓴다(list_parser.parse_total_count).
LIST_TOTAL = ".tab-st4 .tab-btn li.active a"
LIST_ITEM = ".category-feed .feed-item"
LIST_OVERLAY = "a.item-overlay"  # onclick="goView('74445')"
LIST_CATE = ".content .cate"
LIST_NAME = ".content .name"
LIST_STATE = ".content .state"
LIST_PAGE_LINK = "#paginationForm a.page"

# 상세 페이지
DETAIL_CATE = ".cont .cate"
DETAIL_TITLE = ".cont .tit strong"
DETAIL_INFO_ITEM = "ul.info li"
DETAIL_INFO_LABEL = "em"
DETAIL_APPLY = ".btn-group a"
DETAIL_BODY = ".editor-text"

# 상세 ul.info 의 라벨
LABEL_PERIOD = "신청기간"
LABEL_SCHEDULE = "진행일정"
LABEL_TARGET = "대상"
LABEL_ORGANIZATION = "담당기관"
# 필수 라벨(없거나 비면 건별 WARNING). 제목은 별도로 검사하고, 나머지 라벨은 선택 필드다.
REQUIRED_LABELS = {LABEL_PERIOD}

SUMMARY_MAX_LEN = 200


def list_url(page=1, order_by="regYmd desc", per_page=24):
    """목록 URL. 최소 파라미터만 쓴다(지도 관련 파라미터와 #none 은 넣지 않음)."""
    params = {
        "key": KEY,
        "pageIndex": page,
        "orderBy": order_by,
        "recordCountPerPage": per_page,
        "sc_rcritCurentSitu": LIST_STATUS_PARAMS,  # 같은 키를 반복
    }
    return f"{LIST_URL}?{urlencode(params, doseq=True)}"


def detail_url(source_id):
    return f"{DETAIL_URL}?sprtInfoId={source_id}&key={KEY}"
