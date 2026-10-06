# Repository Structure

폴더·파일의 역할입니다. 근거는 [CLAUDE.md](../CLAUDE.md)의 폴더 구조와 각 파일의 주석입니다. 파일 개수와 줄 수는 2026-10-06 기준 git 추적 파일을 센 값이며, 줄 수는 빈 줄을 뺀 값입니다.

```text
.
├─ README.md
├─ CLAUDE.md                  # 개발 규칙·사이트 구조·DB·API 규칙 (작업 기준 문서)
├─ requirements.txt           # 파이썬 의존성 (버전 고정 없음)
├─ pytest.ini
├─ backend/
│  ├─ crawler/                # 수집: Selenium 접속, 목록·상세 파싱, 신청기간 분류, DB 저장
│  ├─ service/                # 표시 규칙(D-Day·그룹·정렬·배지) 순수 함수
│  ├─ api/                    # 읽기 전용 FastAPI
│  ├─ app/                    # 비어 있음, 정리 예정 (아래 참고)
│  └─ data/                   # youth.db 생성 위치 (DB 파일은 git 에 올리지 않음)
├─ frontend/                  # React 화면 (Vite + TypeScript, Vitest)
├─ tests/                     # pytest
├─ notebooks/                 # 탐색용 노트북
├─ scripts/                   # 수동 실행용 배치 파일
└─ docs/                      # 개발 일지, 보조 문서, 이미지
```

## backend

| 폴더 | 파일 수 / 코드 줄 수 (2026-10-06) | 역할 |
|---|---|---|
| `backend/crawler/` | 파이썬 9개 / 1,129줄 (+ 샘플 HTML 5개) | `crawl.py`(실행 진입점, 일일 수집 정책), `browser.py`(Chrome 드라이버), `list_parser.py`·`detail_parser.py`(HTML 파싱), `normalizer.py`(신청기간 분류), `record.py`(DB 한 행 만들기), `db.py`(저장, 변경 감지), `selectors.py`(CSS 셀렉터·URL 상수) |
| `backend/service/` | 2개 / 173줄 | `display.py`: D-Day·표시 상태·그룹·정렬·배지를 계산하는 순수 함수(DB 접근 없음) |
| `backend/api/` | 3개 / 298줄 | `main.py`(엔드포인트), `queries.py`(읽기 전용 조회) |
| `backend/data/` | 추적 파일은 `.gitkeep` 뿐 | `youth.db` 가 만들어지는 위치. `*.db` 는 `.gitignore` 대상 |

- `backend/crawler/samples/` 는 테스트용 HTML 5개(`list_sample.html`, `detail_sample*.html`)입니다. 테스트는 이 파일만 읽고 네트워크에 접속하지 않습니다.
- `backend/app/` 은 **비어 있습니다.** 안에는 `README.md` 한 개(157바이트)만 있고 코드 파일은 없으며, 어디에서도 가져다 쓰지 않습니다. 그 README 는 이 폴더를 FastAPI 를 둘 자리로 설명하는데, 실제 구현 위치는 `backend/api/` 라서 맞지 않는 오래된 문구입니다. **비어 있음, 정리 예정**입니다.

## frontend

| 폴더 | 역할 |
|---|---|
| `frontend/src/api/` | API 호출(`client.ts`), 응답 타입(`types.ts`), 요청 훅(`hooks.ts`) |
| `frontend/src/components/` | 화면 컴포넌트(헤더, 탭, 카드, 달력, 상세 패널, 최근 변경 등) |
| `frontend/src/lib/` | 날짜·달력 격자·점 단계·이벤트 문구 같은 순수 함수와 그 테스트 |
| `frontend/public/` | 아이콘 |

`frontend/src` 는 26개 파일, 2,845줄(테스트 파일 5개 포함)입니다. 자세한 규칙은 [frontend/README.md](../frontend/README.md).

## tests, notebooks, scripts, docs

| 폴더 | 내용 |
|---|---|
| `tests/` | `test_*.py` 12개(파서, 신청기간 분류, DB·변경 감지, 일일 수집 정책, 표시 규칙, API 등), 2,673줄 |
| `notebooks/` | 크롤링 탐색용 노트북 1개 |
| `scripts/` | `run_daily.bat`: **수동 실행용**입니다. 작업 스케줄러는 이 파일을 쓰지 않습니다([scheduler.md](scheduler.md)) |
| `docs/` | `devlog.md`(개발 일지), 이 문서들, `images/`(화면·코드 캡처, 시연 영상) |

## git 에 올리지 않는 것

`.gitignore` 기준: `venv/`, `.venv/`, `__pycache__/`, `*.pyc`, `*.db`, `logs/`, `.ipynb_checkpoints/`, `output/`, `frontend/node_modules/`, `frontend/dist/`.
