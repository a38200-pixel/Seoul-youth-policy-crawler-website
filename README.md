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

결과는 `backend/data/youth.db`, 로그는 `backend/logs/crawl_YYYYMMDD.log`에 저장됩니다.

## 테스트

네트워크 없이 `backend/crawler/samples/`의 HTML만 사용합니다.

```powershell
pytest
```

## 탐색 노트북

```powershell
jupyter notebook notebooks/01_explore_crawling.ipynb
```

## 폴더 구조

```
backend/app/       FastAPI (예정)
backend/crawler/   Selenium 크롤러, 파서, 정규화, DB
backend/data/      youth.db 생성 위치
backend/logs/      실행 로그
frontend/          React (예정)
notebooks/         탐색용 노트북
tests/             pytest
```

자세한 규칙과 사이트 구조는 [CLAUDE.md](CLAUDE.md)를 참고하세요.
