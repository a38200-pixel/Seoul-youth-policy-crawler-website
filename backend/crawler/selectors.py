"""사이트 URL과 CSS 셀렉터 상수. 셀렉터는 이 파일에만 둔다."""

KEY = "2309130006"
BASE_URL = "https://youth.seoul.go.kr/infoData/sprtInfo"
LIST_URL = f"{BASE_URL}/list.do"
DETAIL_URL = f"{BASE_URL}/view.do"

# 수집 대상 모집상태 (마감 제외)
TARGET_STATUSES = ["모집중", "모집예정", "상시"]

# 목록 페이지
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

SUMMARY_MAX_LEN = 200


def detail_url(source_id):
    return f"{DETAIL_URL}?sprtInfoId={source_id}&key={KEY}"
