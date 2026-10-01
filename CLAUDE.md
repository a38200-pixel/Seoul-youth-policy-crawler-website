# 서울 청년정책 마감 D-Day 알리미

청년몽땅정보통(https://youth.seoul.go.kr)의 "청년지원정보"를 매일 수집해
마감 D-Day, 신규/변경 공고, 마감 캘린더를 보여주는 웹서비스.
최종 스택: Python + Selenium(크롤러) / SQLite / FastAPI / React. **AI·LLM은 사용하지 않는다.**
OS는 Windows이며, 이후 Windows 작업 스케줄러로 하루 1회 자동 실행할 예정.

## 진행 방식
- 이 문서(CLAUDE.md)를 기준으로 단계별로 진행한다. 사용자가 지시한 단계만 수행하고, 끝나면 멈춰서 지시를 기다린다.
- **git commit 은 하지 않는다.** 커밋은 사용자가 직접 한다.
- 단계 구분: 1단계 = 폴더 구조·requirements·.gitignore·README·CLAUDE.md / 이후 단계 = 크롤러·노트북·테스트 → FastAPI → React.
- 사이트 구조가 아래 기록과 다르면 추측해서 진행하지 말고 무엇이 다른지 먼저 알린다.

## 폴더 구조
```
youth-dday/ (저장소 루트)
├─ CLAUDE.md
├─ README.md
├─ .gitignore                 # venv, __pycache__, *.db, logs/, .ipynb_checkpoints, output/
├─ requirements.txt           # selenium, pandas, pytest, jupyter
├─ notebooks/
│   └─ 01_explore_crawling.ipynb
├─ backend/
│   ├─ app/                   # FastAPI 자리 (README만)
│   ├─ crawler/
│   │   ├─ samples/           # list_sample.html, detail_sample.html (사용자가 직접 넣음)
│   │   ├─ selectors.py       # CSS 셀렉터·URL 상수를 전부 여기 모음
│   │   ├─ browser.py         # Chrome 드라이버 생성(headless 옵션)
│   │   ├─ list_parser.py     # 목록 페이지 → 공고 기본정보
│   │   ├─ detail_parser.py   # 상세 페이지 → 상세 필드
│   │   ├─ normalizer.py      # 신청기간 문자열 → start_date, end_date
│   │   ├─ record.py          # make_row(list_item, detail) → DB 한 행(dict)
│   │   ├─ db.py              # init_db, upsert_program, deactivate_unseen
│   │   └─ crawl.py           # 실행 진입점: python -m backend.crawler.crawl
│   ├─ data/                  # youth.db 생성 위치
│   └─ logs/                  # 실행 로그
├─ frontend/                  # React 자리 (README만)
└─ tests/
    ├─ test_list_parser.py    # samples/list_sample.html 로 테스트
    ├─ test_detail_parser.py
    └─ test_normalizer.py
```

## 2. 대상 사이트 구조 (사용자가 개발자도구로 확인한 내용)
- 목록 URL: https://youth.seoul.go.kr/infoData/sprtInfo/list.do?key=2309130006
  - GET 파라미터: pageIndex(페이지), recordCountPerPage(8/16/24), orderBy('regYmd desc'=최신순, 'endYmd desc'=마감순),
    sc_rcritCurentSitu(모집상태: 상시/모집중/모집예정/마감, 복수 선택 가능 체크박스), sc_ctgry(분야 코드)
  - 전체 9,254건이므로 모집상태가 '모집중', '모집예정', '상시'인 것만 수집한다.
- 사이트에 접속 대기열(WebGate) 스크립트가 있어서 requests로는 목록이 안 나온다. **반드시 Selenium 브라우저로 접속한다.**
  처음엔 목록 URL로 접속해 목록이 뜰 때까지 기다리고, 같은 드라이버 세션으로 계속 이동한다.
- 목록 항목: `.category-feed .feed-item`
  - 공고 ID: `a.item-overlay` 의 onclick 속성 `goView('74445')` 에서 숫자 추출
  - 분야: `.content .cate` (비어 있을 수 있음)
  - 제목: `.content .name`
  - 모집상태: `.content .state` (모집중/모집예정/상시/마감)
- 페이지네이션: `#paginationForm a.page` (onclick="fn_egov_link_page(2)"). 다음 페이지는 클릭 대신
  pageIndex 파라미터를 바꾼 URL로 driver.get 한다. 항목이 0개인 페이지가 나오면 종료.
- 상세 URL: https://youth.seoul.go.kr/infoData/sprtInfo/view.do?sprtInfoId={ID}&key=2309130006
  - 분야 `.cont .cate`, 제목 `.cont .tit strong`
  - `ul.info li` 마다 `<em>` 라벨 + 나머지 텍스트: '신청기간', '진행일정', '대상', '담당기관'
    (**라벨 기준으로 찾을 것. 순서에 의존하지 말 것**)
  - 신청 링크: `.btn-group a` 의 href / 본문: `.editor-text` 텍스트 앞 200자만 summary로 저장
  - 신청기간 예: "2026-09-29 ~ 2026-10-09\n 00 : 00" (공백·줄바꿈·시간 섞임)

## 3. 탐색용 노트북 (notebooks/01_explore_crawling.ipynb)
사용자의 기존 스타일처럼 셀 단위로 하나씩 실행하며 확인할 수 있게 만든다:
- 셀1 import
- 셀2 webdriver.Chrome() 으로 목록 접속 + WebDriverWait
- 셀3 find_elements 로 첫 페이지 항목 출력
- 셀4 상세 페이지 1건 접속해 ul.info 라벨별 값 출력
- 셀5 신청기간 파싱 결과 출력
- 셀6 2페이지까지 돌려 CSV 저장
각 셀 위에 "무엇을 확인하는 셀인지" 마크다운 설명을 단다.

## 4. 크롤러 코드 규칙
- 스타일: selenium의 By.CSS_SELECTOR, WebDriverWait + expected_conditions 사용. time.sleep만으로 대기하지 말 것.
- 항목 단위로 하위 요소를 찾는다(리스트를 따로 모아 인덱스로 맞추는 방식 금지).
- 셀렉터는 selectors.py 에만 둔다. 요소가 없으면 None 처리하고 경고 로그를 남긴다(크래시 금지).
- 페이지 이동마다 1초 이상 대기. 재시도는 최대 2회.
- headless 옵션은 crawl.py 실행 인자 `--headless` 로 켜고 끈다. 그 밖의 인자: `--max-pages`(테스트용), `--no-detail`.
- normalizer: 'YYYY-MM-DD ~ YYYY-MM-DD' 패턴을 추출. 날짜를 못 찾으면 start/end는 None, 원문은 period_text에 보관.
  `classify_period(text)` 가 (period_type, start, end) 를 반환: dated / always("상시"로 시작) / unknown(경고 로그).
  모든 날짜 기준 시간대는 Asia/Seoul.
- 마지막에 수집 건수, 상세 성공/실패 건수, 소요 시간을 logs/crawl_YYYYMMDD.log 와 콘솔에 출력.
- 이미 DB에 있고 last_seen_at 이 오늘인 공고는 상세를 다시 방문하지 않는다(재실행 시 부담 줄이기).

## 5. SQLite (backend/data/youth.db)
- `programs` 테이블: id INTEGER PK, source_id TEXT UNIQUE, title, category, organization, target, summary,
  period_text, period_type TEXT, schedule_text TEXT, start_date DATE, end_date DATE, source_status, source_url,
  apply_url, is_active INTEGER, first_seen_at DATETIME, last_seen_at DATETIME, updated_at DATETIME
  - period_type: 'dated'(신청기간에 날짜 범위 있음) / 'always'(날짜 없이 "상시"로 시작, start/end 는 NULL) / 'unknown'(그 외, 경고 로그)
  - period_text: 신청기간 원문(공백 정리). 예: "상시 [ 선착순 마감 ]"
  - schedule_text: 진행일정 원문(공백 정리). 예: "2026-11-07 00:00:00 14시 0분 ~ 15시 30분"
  - start_date/end_date 는 **신청기간에서만** 만든다. 진행일정 날짜를 end_date 로 쓰지 않는다.
- source_id 기준 upsert. 신규면 first_seen_at 기록, 기존이면 값 갱신 + last_seen_at 갱신.
- 이번 실행에서 보이지 않은 공고는 is_active=0 (삭제하지 않음).
- **is_active 갱신은 전체 수집이 완료됐을 때만** 한다. `--max-pages` 로 일부만 수집했거나 중간에 실패·중단된 실행에서는
  `deactivate_unseen` 을 호출하지 않는다(안 그러면 안 본 공고가 전부 비활성이 된다). 호출 규칙은 crawl.py(4-B)에서 구현.
  `deactivate_unseen` 은 seen_ids 가 비어 있으면 ValueError. `upsert_program` 은 본 공고를 is_active=1 로 되살린다.
- 날짜·시각은 DB에 isoformat() 문자열로 저장한다(Python 3.12 sqlite3 기본 adapter 가 deprecated). 시각 기준은 Asia/Seoul.

### record.py / db.py 역할
- `record.make_row(list_item, detail)`: 목록 항목 + parse_detail 결과 → DB 한 행.
  - title/category 는 상세 우선, 없으면 목록 값. source_status 는 목록의 모집상태. source_url 은 상세 URL 규칙대로 생성.
  - period_type/start_date/end_date 는 `classify_period(detail["period_text"])` 결과로만 만든다(schedule_text 는 넘기지 않음).
  - detail 이 None(상세를 받지 않음)이면 상세 필드와 period_type 은 None('unknown' 아님).
- `db.init_db(path)`: programs, program_changes 생성, 연결 반환(':memory:' 가능).
- `db.upsert_program(conn, row, now)`: source_id 기준. 신규면 True, 갱신이면 False 반환. commit 은 호출자가 한다.
  - row 값이 None 이면 기존 값을 덮어쓰지 않는다. **예외: period_type/start_date/end_date 는 한 묶음**이라
    period_type 이 None(상세 미수신)이면 셋 다 유지, 값이 있으면 start/end 가 None 이어도 덮어쓴다
    (dated → always 로 바뀐 공고에 옛 end_date 가 남지 않게). 반대로 상세에서 값이 비게 된 organization 등은 비워지지 않는다.
  - last_seen_at, updated_at 은 항상 now 로 갱신.
- `db.deactivate_unseen(conn, seen_ids)`: seen_ids 에 없으면 is_active=0, 있으면 1. 새로 비활성이 된 행 수 반환.
- `program_changes` 테이블(id, program_id, change_type, old_value, new_value, detected_at)은 스키마만 만들어 둔다.
  변경 감지 로직은 다음 단계에서 구현한다.

### D-Day 규칙
- dated: D-Day = end_date - 오늘(Asia/Seoul). 오늘 기준으로 아래 둘로 나뉜다.
  - 모집중(start_date <= 오늘): 마감 D-Day 순으로 정렬(마감 임박이 먼저).
  - 모집예정(오늘 < start_date): 마감 D-Day 대신 **'시작 D-n'**(start_date - 오늘)으로 표시하고,
    모집중 뒤에 정렬한다(시작일 빠른 순).
- always: **D-Day 없음, 목록 맨 뒤**에 둔다.
- unknown: D-Day 계산 불가, **목록 맨 뒤**에 둔다. 화면 표시는 always 와 구분해서 다룰 것(UI 단계에서 정함).
- 정렬 순서: 모집중(dated) → 모집예정(dated) → always, unknown.
- 진행일정(schedule_text)은 D-Day 기준으로 쓰지 않는다. 표시용 텍스트일 뿐이다.

## 6. 테스트와 확인
- tests 는 samples/ 의 HTML을 파일로 읽어 파싱 함수만 검증한다(네트워크 접속 없이). pytest 로 실행.
- 다 만든 뒤 `python -m backend.crawler.crawl --max-pages 1` 을 실행해서 실제로 수집되는지 확인하고,
  결과 건수와 DB 샘플 3행을 보여준다. 실패하면 원인을 설명하고 고친다.
- 사이트 구조가 위 기록과 다르면 추측해서 진행하지 말고 무엇이 다른지 먼저 알린다.
