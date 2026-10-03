# 서울 청년정책 마감 D-Day 알리미

청년몽땅정보통(https://youth.seoul.go.kr)의 "청년지원정보"를 매일 수집해 마감 D-Day, 신규/변경 공고, 마감 캘린더를 보여주는 웹서비스.

- 스택: Python + Selenium(크롤러) / SQLite / FastAPI / React (AI·LLM 미사용)
- 현재 단계: 크롤러 + SQLite 저장 + 읽기 전용 FastAPI API 구현 완료, React 화면은 예정(`frontend/` 는 자리만)

## 주요 기능

- **D-Day 정렬**: 신청기간의 마감일 기준으로 모집중(마감 임박 순) → 모집예정(시작 D-n) → 마감일 미정 → 상시 → 확인 필요 순으로 정렬. 날짜만 쓰고 시각은 무시한다.
- **변경 감지**: 신규(NEW), 마감 연장·단축, 신청기간 변경, 모집상태 변경, 목록에서 내려감(마감 만료 / 마감 전 내려감), 재등록을 `program_changes` 에 기록하고 배지로 보여준다.
- **읽기 전용 API**: FastAPI 로 목록·상세·변경 목록·메타 정보를 제공한다. DB 에는 쓰지 않는다.
- 기술 스택: Python, Selenium(크롤러), SQLite, FastAPI. 프론트엔드(React)는 아직 없다. 개발 일지는 [docs/devlog.md](docs/devlog.md).

## 설치 (Windows, PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Chrome 브라우저가 설치되어 있어야 합니다(Selenium Manager가 드라이버를 자동으로 받습니다).

이 저장소는 Windows 의 conda 환경 `web_crawling` 에서 개발·실행했습니다(`python.exe` 경로 예: `%USERPROFILE%\anaconda3\envs\web_crawling\python.exe`). venv 대신 conda 환경을 써도 `pip install -r requirements.txt` 는 같습니다.

## 실행

프로젝트 루트에서 실행합니다.

```powershell
# 크롤링 (브라우저 창 표시)
python -m backend.crawler.crawl

# headless, 1페이지만, 상세 페이지 생략 등
python -m backend.crawler.crawl --headless --max-pages 1
python -m backend.crawler.crawl --no-detail
```

| 인자 | 설명 |
|---|---|
| `--headless` | 브라우저 창 없이 실행 |
| `--max-pages N` | 테스트용 최대 페이지 수 |
| `--no-detail` | 상세 페이지 방문 생략 |
| `--detail-limit N` | 상세를 최대 N건만 받음 (부분 실행) |
| `--daily` | 일일 수집: 목록 전체를 읽고 정책 대상(신규·상시 외·상태 변경·오래된 상시)만 상세를 받음 |
| `--daily-plan` | 사이트 접속 없이 DB 만 읽기 전용으로 읽어 `--daily` 의 대상 건수를 출력 |
| `--reclassify` | 사이트 접속 없이 DB 의 신청기간 분류를 다시 계산 |

결과는 `backend/data/youth.db`, 로그는 `backend/logs/crawl_YYYYMMDD.log`에 저장됩니다.

종료 코드(`backend/crawler/crawl.py` 기준): 0 정상(부분 실행 포함, `--reclassify`·`--daily-plan` 성공 포함) / 1 목록을 끝까지 읽지 못함(일부 페이지 실패 또는 상한 도달) / 2 목록 0건·제외 후 대상 0건(DB 변경 없음), `--reclassify`·`--daily-plan` 에서 DB 파일이 없거나 `--daily-plan` 의 스키마가 오래됨, 잘못된 인자 / 3 `run_crawl` 중 예기치 못한 예외 / 4 상세 연속 실패로 중단(1 과 겹치면 4 가 우선).

## 신청기간 분류와 D-Day 계산

신청기간 원문(`period_text`)을 `classify_period` 가 다음 중 하나로 분류해 `period_type` 에 저장합니다. 판정 순서는 dated → end_only → open → always → unknown 입니다.

| period_type | 의미 | start_date / end_date | D-Day |
|---|---|---|---|
| `dated` | 날짜 범위가 있음 | 둘 다 | 마감 D-Day(`end_date − 오늘`). 시작일이 미래면 모집예정 '시작 D-n' |
| `end_only` | 시작일 없이 "~ YYYY-MM-DD" | end 만 | dated 처럼 end_date 기준. 상태는 목록의 모집상태 사용 |
| `open` | 마감일 미정 | start 만(있으면) | 없음, '마감일 미정' 배지 |
| `always` | "상시"로 시작 | 없음 | 없음, 목록 뒤쪽 |
| `unknown` | 해석 불가(경고 로그) | 없음 | 없음, '확인 필요' |

- `start_date`/`end_date` 는 **신청기간에서만** 만듭니다. 상세의 **진행일정(`schedule_text`)은 마감일로 쓰지 않고** 표시용으로만 저장합니다.
- 시각(예: "18 : 00")은 무시하고 날짜만 씁니다. 모든 날짜 기준 시간대는 Asia/Seoul 입니다.
- 시작일이 미래면 사이트 모집상태가 '모집중'이어도 날짜를 우선해 모집예정으로 표시합니다. 분야가 없는 상시 공고는 '상시-기타'로 두고 기본 목록에서 숨깁니다.
- 상세 규칙은 [CLAUDE.md](CLAUDE.md) 를 참고하세요.

## 일일 수집 정책 (`--daily`)

목록은 전체를 읽고, 상세 페이지는 다음 대상만 받습니다(중복 제거, 앞 구분이 우선).

| 구분 | 대상 |
|---|---|
| 신규 | DB 에 없거나 상세를 받은 적 없는 행 |
| 상시 외 매일 | 활성 `dated`/`end_only`/`open`/`unknown` 행 |
| 상태 변경 | 목록의 모집상태가 DB 와 달라진 행 |
| 상시 갱신 | 활성 `always` 중 상세를 받은 지 7일 이상 지난 행(오래된 순, 최대 200건) |

`--daily-plan` 은 사이트에 접속하지 않고 DB 를 읽기 전용으로 읽어 대상 건수를 미리 보여줍니다.

안전장치:
- 목록을 끝까지 정상으로 읽은 **완전 수집일 때만** 목록에서 사라진 공고를 비활성(`is_active=0`) 처리합니다. `--max-pages`·`--detail-limit` 을 쓴 부분 실행과 중단된 실행에서는 하지 않습니다.
- 수집 건수가 직전 활성 공고 수의 **50% 미만**이면 비활성 처리를 하지 않고 경고합니다.
- 상세 요청이 **연속 10건 실패**하면 수집을 중단합니다(종료 코드 4, 비활성 처리 안 함).
- 상세를 마지막으로 받은 시각(`detail_fetched_at`)의 날짜가 **오늘이면 다시 요청하지 않습니다**(재실행 부담 감소).

## 자동 수집 (Windows 작업 스케줄러)

| 항목 | 값 |
|---|---|
| 작업 이름 | `SeoulYouthDaily` |
| 실행 시각 | 매일 07:00 |
| 놓친 실행 | 가능한 한 빨리 시작 |
| 제한 시간 | 2시간 |
| 동작 | 콘다 환경의 `python.exe` 를 직접 호출: `-m backend.crawler.crawl --daily --headless` |
| 시작 위치(작업 디렉터리) | 프로젝트 루트(저장소 최상위 폴더) — `-m backend.crawler.crawl` 은 프로젝트 루트에서 실행해야 함 |

- [scripts/run_daily.bat](scripts/run_daily.bat) 은 **수동 실행용**이며 스케줄러는 사용하지 않습니다. 처음에 이 `.bat` 을 스케줄러에 연결했더니 작업 결과가 `3221225477`(0xC0000005)로 나왔고, 이벤트 로그상 크래시한 것은 파이썬이 아니라 `cmd.exe` 였습니다. 같은 `.bat` 은 일반 터미널에서는 정상 동작했고 원인은 규명하지 못했습니다(원인 미상). 자세한 내용은 [docs/devlog.md](docs/devlog.md).
- 한계: **PC 가 켜져 있고 로그인된 상태여야 실행**됩니다. PC 가 켜져 있지 않거나 로그인되지 않은 날은 실행되지 않아 수집 공백이 생길 수 있습니다.

## 테스트

네트워크 없이 `backend/crawler/samples/`의 HTML만 사용합니다.

```powershell
pytest
```

2026-10-03 에 `pytest -v` 를 실행한 결과: 363 passed, 1 warning (경고는 starlette 의 `httpx2` 설치 안내).

## API 서버 (읽기 전용)

```powershell
uvicorn backend.api.main:app --reload
```

- http://127.0.0.1:8000 에서 열리고 `/docs` 에서 확인할 수 있습니다. DB 에는 **쓰지 않으며**(요청마다 읽기 전용으로 엽니다) 쓰기 엔드포인트가 없습니다.
- DB 경로는 환경변수 `YOUTH_DB_PATH` (기본 `backend/data/youth.db`). DB 파일이 없으면 만들지 않고 503 을 돌려줍니다.
  예: `$env:YOUTH_DB_PATH = "C:\path\to\copy.db"; uvicorn backend.api.main:app --reload`
- CORS 는 `http://localhost:5173`, `http://127.0.0.1:5173` 만 허용합니다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/health` | 상태 확인 (`status`, `db_available`) |
| GET | `/api/meta` | 오늘 날짜, 활성 건수, 탭별 건수, 분야 목록(`categories`: 이름·건수, 많은 순), 마지막 수집 시각(활성 행의 `last_seen_at` 최댓값, 재분류는 반영 안 됨), 최근 7일 변경 종류별 건수, 기준일 |
| GET | `/api/programs` | 활성 공고 목록. `tab`(deadline 기본 / always / etc / all), `q`, `category`, `group`(recruiting / upcoming / open / always / always_etc / unknown), `date`(`YYYY-MM-DD`, 그 날짜가 마감일인 공고만), `limit`(기본 50, 최대 200), `offset`. 응답의 `counts`·`group_counts` 는 `group`·`date` 와 무관 |
| GET | `/api/calendar?month=YYYY-MM` | 월별 마감 달력. 마감일(end_date)이 그 달인 모집중·모집예정 공고의 날짜별 건수(`days`: 건수가 1 이상인 날짜만). `q`, `category` 사용 가능 |
| GET | `/api/programs/{source_id}` | 공고 상세 + 변경 이력(최신순). 없으면 404, 비활성 행도 200 |
| GET | `/api/changes?days=7&type=` | 최근 변경 목록(NEW 포함, 시각 내림차순). 항목마다 `end_date`·`period_type`(공고 행이 없으면 null) |

## 탐색 노트북

```powershell
jupyter notebook notebooks/01_explore_crawling.ipynb
```

## 폴더 구조

```
backend/api/       읽기 전용 FastAPI (main.py, queries.py)
backend/service/   표시 규칙(D-Day·그룹·정렬·배지) 순수 함수
backend/app/       (사용 안 함)
backend/crawler/   Selenium 크롤러, 파서, 정규화, DB
backend/data/      youth.db 생성 위치
backend/logs/      실행 로그
frontend/          React (예정)
notebooks/         탐색용 노트북
scripts/           run_daily.bat (수동 실행용)
docs/              개발 일지(devlog.md)
tests/             pytest
```

## 알려진 한계

- 공고 변경은 하루 1회(07:00) 수집 시점에 반영됩니다. 사이트 구조(셀렉터)가 바뀌면 수집이 깨질 수 있습니다.
- 변경 감지는 첫 실데이터 검증(2026-10-02 → 10-03, 표본 1일)에서 연장·단축 이벤트가 한 건도 관찰되지 않아, 연장·단축 판정은 실제 사례로 확인하지 못했습니다.
- 기준일(2026-10-01)에 처음 적재한 공고는 NEW 로 표시하지 않습니다. 재분류(`--reclassify`)는 변경 이벤트를 만들지 않습니다.
- 모집상태가 '모집예정'인 `end_only` 공고는 시작일을 몰라 '시작 D-n' 을 만들 수 없습니다(화면 표시 방식은 UI 단계에서 결정).
- API 에는 인증이 없고 읽기 전용입니다. CORS 는 `localhost:5173`, `127.0.0.1:5173` 만 허용합니다.
- 자동 수집은 PC 가 켜져 있고 로그인된 상태여야 하며, 꺼져 있던 날은 수집 공백이 생길 수 있습니다.
- 다음은 **가설**이며 아직 검증하지 않았습니다(근거와 검증 기준은 [docs/devlog.md](docs/devlog.md) 3번 항목).
  - 사이트가 상시 게시글을 등록 약 1년 뒤에 숨기는 것으로 보임(활성 상시의 최소 ID 64782).
  - 신청기간이 불완전한 글(시작일만 또는 종료일만 있는 글)은 1~2일 안에 사라지는 경향(9건 중 9건, 표본 작음).
- React 화면과 캘린더(.ics) 내보내기는 아직 없습니다.

## AI 도구 사용 고지

이 서비스의 기능에는 AI(LLM)를 사용하지 않습니다. 개발 과정에서는 코드 작성 도구로 Claude Code 를 사용했습니다. 설계와 검수는 개발자가 했고, AI 는 구현을 도왔습니다.

## 스크린샷

`docs/images/` 폴더는 아직 없고 아래 파일도 없습니다. 파일을 넣은 뒤 `![설명](docs/images/파일명)` 링크를 추가하세요.

| 파일명 | 내용 | 상태 |
|---|---|---|
| `api-docs.png` | API 문서(`/docs`) 화면 | `TODO(확인 필요)` 파일 없음 |
| `api-changes.png` | `/api/changes` 응답 | `TODO(확인 필요)` 파일 없음 |
| `pytest.png` | pytest 실행 결과 | `TODO(확인 필요)` 파일 없음 |
| `daily-log-summary.png` | `--daily` 실행 요약 로그 | `TODO(확인 필요)` 파일 없음 |
| `scheduler-task.png` | 작업 스케줄러 `SeoulYouthDaily` 설정 | `TODO(확인 필요)` 파일 없음 |

자세한 규칙과 사이트 구조는 [CLAUDE.md](CLAUDE.md)를 참고하세요.
