# 서울 청년정책 마감 D-Day 알리미

청년몽땅정보통(https://youth.seoul.go.kr)의 "청년지원정보"를 매일 수집해 마감 D-Day, 신규/변경 공고, 마감 캘린더를 보여주는 웹서비스.

- 스택: Python + Selenium(크롤러) / SQLite / FastAPI / React (AI·LLM 미사용)
- 현재 단계: 1단계 — 폴더 구조 + 크롤러 + SQLite 저장 (FastAPI·React는 자리만)

## 설치 (Windows, PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Chrome 브라우저가 설치되어 있어야 합니다(Selenium Manager가 드라이버를 자동으로 받습니다).

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

## 테스트

네트워크 없이 `backend/crawler/samples/`의 HTML만 사용합니다.

```powershell
pytest
```

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
| GET | `/api/meta` | 오늘 날짜, 활성 건수, 탭별 건수, 마지막 수집 시각(활성 행의 `last_seen_at` 최댓값, 재분류는 반영 안 됨), 최근 7일 변경 종류별 건수, 기준일 |
| GET | `/api/programs` | 활성 공고 목록. `tab`(deadline 기본 / always / etc / all), `q`, `category`, `limit`(기본 50, 최대 200), `offset` |
| GET | `/api/programs/{source_id}` | 공고 상세 + 변경 이력(최신순). 없으면 404, 비활성 행도 200 |
| GET | `/api/changes?days=7&type=` | 최근 변경 목록(NEW 포함, 시각 내림차순) |

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
tests/             pytest
```

자세한 규칙과 사이트 구조는 [CLAUDE.md](CLAUDE.md)를 참고하세요.
