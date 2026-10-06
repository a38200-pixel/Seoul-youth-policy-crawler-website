# 설치와 실행

Windows(PowerShell)에서 개발·실행했습니다. 모든 명령은 별도 표시가 없으면 **프로젝트 루트**에서 실행합니다.

## 개발 환경 (2026-10-06 확인값)

| 항목 | 값 | 비고 |
|---|---|---|
| Python | 3.12.14 | 개발에 쓴 conda 환경 `web_crawling` 의 버전. 최소 요구 버전을 정해 둔 파일은 없습니다 |
| Node.js | v24.18.0 (npm 11.16.0) | 개발에 쓴 버전. `package.json` 에 `engines` 지정은 없습니다 |
| 브라우저 | Chrome | Selenium 이 Chrome 을 띄웁니다. 드라이버는 Selenium Manager 가 자동으로 받습니다 |

- **`requirements.txt` 는 버전을 고정하지 않았습니다.** 패키지 이름만 있습니다(selenium, beautifulsoup4, tzdata, pandas, pytest, jupyter, fastapi, uvicorn, httpx). 시간이 지나 설치하면 개발 때와 다른 버전이 받아질 수 있습니다.
- 프런트엔드는 `frontend/package.json` 에 버전 범위가 있고(`react ^19.2.8`, `vite ^8.3.0`, `typescript ~6.0.2`, `vitest ^5.0.3` 등) `package-lock.json` 이 있습니다.

## 설치

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

venv 대신 conda 환경을 써도 `pip install -r requirements.txt` 는 같습니다. 이 저장소는 conda 환경 `web_crawling` 에서 개발·운영했습니다.

프런트엔드:

```powershell
cd frontend
npm install
```

## 수집 실행

```powershell
# 브라우저 창을 띄워서 실행
python -m backend.crawler.crawl

# 창 없이, 목록 1페이지만
python -m backend.crawler.crawl --headless --max-pages 1

# 상세 페이지 방문 생략
python -m backend.crawler.crawl --no-detail

# 일일 수집(자동 수집이 쓰는 방식)
python -m backend.crawler.crawl --daily --headless

# 사이트에 접속하지 않고 일일 수집 대상 건수만 보기(DB 를 읽기 전용으로 읽음)
python -m backend.crawler.crawl --daily-plan
```

인자 설명과 종료 코드는 [daily_crawl_policy.md](daily_crawl_policy.md)에 있습니다. 결과는 `backend/data/youth.db`, 로그는 `backend/logs/crawl_YYYYMMDD.log` 에 저장됩니다(둘 다 git 에 올리지 않습니다).

## 백엔드(API) 실행

```powershell
uvicorn backend.api.main:app --reload
```

- http://127.0.0.1:8000 에서 열리고, `/docs` 에서 자동 문서를 볼 수 있습니다. 엔드포인트는 [api_reference.md](api_reference.md)에 정리했습니다.
- DB 경로는 환경변수 `YOUTH_DB_PATH` 로 바꿉니다(기본 `backend/data/youth.db`). 예: `$env:YOUTH_DB_PATH = "<DB 파일 경로>"; uvicorn backend.api.main:app --reload`
- DB 는 읽기 전용으로 열고, 파일이 없으면 만들지 않고 503 을 돌려줍니다.

## 화면(React) 실행

터미널 2개를 씁니다.

```powershell
# 터미널 1: 백엔드 (프로젝트 루트)
uvicorn backend.api.main:app --reload

# 터미널 2: 프런트엔드
cd frontend
npm run dev
```

- 접속 주소: http://localhost:5173
- 개발 도구가 `/api` 요청을 `http://127.0.0.1:8000` 으로 넘겨 줍니다. 다른 포트의 백엔드를 쓰려면 환경변수 `API_PROXY_TARGET` 으로 바꿉니다. 예: `$env:API_PROXY_TARGET = "http://127.0.0.1:8001"; npm run dev`

## 테스트

```powershell
# 백엔드 (프로젝트 루트). 네트워크에 접속하지 않고 backend/crawler/samples/ 의 HTML 만 씁니다
pytest -q

# 프런트엔드
cd frontend
npm test
npm run build
npm run lint
```

최근 실행 결과는 README 의 "검증 결과"를 참고하세요.

## 자동 실행

Windows 작업 스케줄러 설정은 [scheduler.md](scheduler.md)를 참고하세요. `scripts/run_daily.bat` 은 수동 실행용입니다.
