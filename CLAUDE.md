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
  `classify_period(text)` 가 (period_type, start, end) 를 반환: dated / end_only("~ YYYY-MM-DD" 로 시작, 시작일 없음) /
  always("상시"로 시작) / unknown(경고 로그). 판정 순서는 dated → end_only → always → unknown. end_only 의 날짜가 유효하지 않으면 unknown.
  모든 날짜 기준 시간대는 Asia/Seoul.
- 마지막에 수집 건수, 상세 성공/실패 건수, 소요 시간을 logs/crawl_YYYYMMDD.log 와 콘솔에 출력.
- 상세를 **마지막으로 받은 시각(`detail_fetched_at`)의 날짜(Asia/Seoul)가 오늘이면** 상세를 다시 방문하지 않는다(재실행 시 부담 줄이기).
  판정에 `last_seen_at` 을 쓰지 않는다: 목록만 본 upsert 도 last_seen_at 을 오늘로 갱신하므로, 어제 받은 상세를 오늘 받은 것으로 오인하게 된다.
  `detail_fetched_at` 은 상세를 받은 upsert 에서만 갱신하고(목록만 본 upsert·상세 수신 실패는 그대로), NULL 이면 받은 적 없는 것으로 본다.
  오늘 날짜는 `run_crawl(..., today=date)` 로 주입할 수 있다(테스트용).

### 목록 URL 구조 (최소 파라미터)
사용자가 주소창에서 확인한 URL 에서 지도 관련 파라미터(cntrLa, cntrLo, neLat, neLng, swLat, swLng, mapLvl, sarea, viewType)와
`#none` 을 뺀 최소형을 `selectors.list_url(page=1, order_by="regYmd desc", per_page=24)` 로 만든다.
```
https://youth.seoul.go.kr/infoData/sprtInfo/list.do?key=2309130006&pageIndex=1&orderBy=regYmd+desc&recordCountPerPage=24
  &sc_rcritCurentSitu=상시&sc_rcritCurentSitu=모집중&sc_rcritCurentSitu=모집예정   (같은 키 3회 반복, 한글은 퍼센트 인코딩)
```
- 최소 URL 이 전체 URL 과 같은 결과("전체 N건")를 주는지는 실행 검증 a) 에서 확인한다.
- 제외 공고: `selectors.EXCLUDE_IDS`(초기값 68721), `EXCLUDE_TITLE_KEYWORDS`(초기값 "게시요청 가이드"). 제외 건수와 제목은 로그에 남긴다.
- "전체 N건" 은 `.tab-st4 .tab-btn li.active a` 선택자로 읽되, **`.tab-st4` 가 두 군데(정렬 탭, 건수 탭)에 있고**
  텍스트가 '전체 N건' 형태인 것만 쓴다. 정렬 탭의 active 링크는 "최신순"(문서 순서상 첫 번째), 건수 탭은 "전체 9254건"
  (+ "상시지원 N건", "일반지원 N건"). 판별 정규식은 `r"전체\s*([\d,]+)건"`.
- 실행 끝 건수 비교는 `수집 + 제외 + 대상 외 상태 = 목록에서 읽은 건수` 를 예상 건수("전체 N건")와 비교한다.
  페이지 사이에 중복된 source_id 가 있으면 건수와 ID 를 요약에 출력한다.

### crawl.py 실행 (프로젝트 루트, conda 환경 web_crawling)
```
python -m backend.crawler.crawl [--headless] [--max-pages N] [--no-detail] [--detail-limit N]
```
- `--headless` 창 없이 실행 / `--max-pages N` 목록 N페이지만(부분 실행) / `--no-detail` 상세 방문 생략 / `--detail-limit N` 상세를 최대 N건만 받음(부분 실행).
- `--reclassify`: **사이트 접속 없이** DB 의 period_text 로 period_type/start_date/end_date 를 다시 계산한다
  (`python -m backend.crawler.crawl --reclassify`). 바뀐 행만 갱신(updated_at 갱신, last_seen_at 은 그대로)하고, period_text 가 NULL 인
  행(상세 미수신)은 건드리지 않는다. 실행 후 바뀐 행 수·ID(이전→이후)와 DB 전체 period_type 별 건수를 출력한다. DB 파일이 없으면
  새로 만들지 않고 종료 코드 2. 분류 규칙을 바꾼 뒤 이미 저장된 행에 적용할 때 쓴다.
  일반 실행에서도 목록 수집이 성공해 DB 를 연 직후(upsert 전)에 같은 재분류를 자동으로 한 번 한다(목록 0건이면 DB 를 열지 않으므로 하지 않음).
- 로그 수준: 필수 필드(제목, 신청기간)의 "라벨 없음"/"값 비어 있음" 만 건별 WARNING. 선택 필드(대상·진행일정·담당기관)는 건별 DEBUG 로
  내리고, 실행 요약에 "선택 필드 비어 있음(상세 받은 N건 중): 대상 N건, …" 으로 필드별 건수를 출력한다.
- 흐름: 목록(24건/페이지, pageIndex 로 이동, 항목 0개 페이지에서 종료, 상한 300페이지) → 제외·상태 필터 → 항목마다
  (detail_fetched_at 이 오늘이면 상세 건너뜀, 아니면 상세 수신) → make_row → upsert_program → commit.
  목록에서 0건이면 DB 를 만들지도 열지도 않는다. 변경 감지(program_changes 기록)는 다음 단계.
- 대기: `.category-feed` 가 나타날 때까지 WebDriverWait(60초, 상세 30초). 타임아웃이면 재시도 최대 2회 후
  `backend/logs/timeout_*.png` 스크린샷을 저장하고 로그에 남긴다. 이동 사이 최소 1초 대기.
- **is_active 갱신(deactivate_unseen)은 `--max-pages`/`--detail-limit` 없이 목록을 끝까지 정상으로 읽은 실행에서만** 호출한다.
  부분 실행이면 "부분 실행이라 is_active 갱신 생략" 을 남긴다. 전체 실행이어도 수집 건수가 직전 활성 공고 수의 50% 미만이면
  호출하지 않고 경고한다(직전 활성이 없는 첫 전체 실행은 검사 생략).
- 목록 페이지 전체가 이미 본 공고로만 채워지면(범위 밖 pageIndex 에 마지막 페이지가 반복되는 경우) 목록 끝으로 본다.
- 종료 코드: 0 정상(부분 실행 포함) / 1 목록 일부 실패·상한 도달로 전체 완료 못 함 / 2 목록 0건 또는 첫 페이지 실패(DB 변경 없음) / 3 예기치 못한 오류.
- 실행 끝에 요약을 콘솔과 `backend/logs/crawl_YYYYMMDD.log` 에 출력: 목록 수집·제외 건수, 예상 건수("전체 N건") 비교
  (부분 실행이면 비교 생략), 신규/갱신, 상세 성공/실패/건너뜀, period_type 별 건수, 분야가 빈 공고, unknown 신청기간 원문 전부, 소요 시간.

## 5. SQLite (backend/data/youth.db)
- `programs` 테이블: id INTEGER PK, source_id TEXT UNIQUE, title, category, organization, target, summary,
  period_text, period_type TEXT, schedule_text TEXT, start_date DATE, end_date DATE, source_status, source_url,
  apply_url, is_active INTEGER, first_seen_at DATETIME, last_seen_at DATETIME, updated_at DATETIME,
  detail_fetched_at DATETIME
  - detail_fetched_at: 상세를 마지막으로 받은 시각(isoformat, KST). 상세를 받은 upsert 에서만 갱신, 미수신이면 NULL.
    기존 DB 는 init_db 가 `ALTER TABLE` 로 컬럼을 추가하며 **백필하지 않는다**(기존 행은 NULL → 다음 실행에서 상세를 한 번 다시 받음).
  - period_type: 'dated'(신청기간에 날짜 범위 있음) / 'end_only'(시작일 없이 "~ YYYY-MM-DD", start_date 는 NULL·end_date 만 채움) /
    'always'(날짜 없이 "상시"로 시작, start/end 는 NULL) / 'unknown'(그 외, 경고 로그). 상세를 받지 않은 행은 NULL.
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
- end_only: **dated 처럼 end_date 기준 D-Day**(end_date - 오늘). start_date 가 없으므로 **상태는 목록의 모집상태(source_status)를 사용**한다.
  (사이트 원본에 시작일이 비어 있는 공고다. 예: 74531 신청기간 "~ 2026-10-08 00 : 00", 목록 상태 모집중.)
  모집상태가 모집예정인 end_only 는 시작일을 모르므로 '시작 D-n' 을 만들 수 없다 — 표시 방식은 UI 단계에서 정한다.
- unknown: D-Day 계산 불가, **목록 맨 뒤**에 둔다. 화면 표시는 always 와 구분해서 다룰 것(UI 단계에서 정함).
- 정렬 순서: 모집중(dated, end_only) → 모집예정(dated) → always, unknown.
- 진행일정(schedule_text)은 D-Day 기준으로 쓰지 않는다. 표시용 텍스트일 뿐이다.

## 6. 테스트와 확인
- tests 는 samples/ 의 HTML을 파일로 읽어 파싱 함수만 검증한다(네트워크 접속 없이). pytest 로 실행.
- 다 만든 뒤 `python -m backend.crawler.crawl --max-pages 1` 을 실행해서 실제로 수집되는지 확인하고,
  결과 건수와 DB 샘플 3행을 보여준다. 실패하면 원인을 설명하고 고친다.
- 사이트 구조가 위 기록과 다르면 추측해서 진행하지 말고 무엇이 다른지 먼저 알린다.
