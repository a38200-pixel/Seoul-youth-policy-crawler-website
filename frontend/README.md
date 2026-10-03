# frontend (React 화면)

서울 청년정책 마감 D-Day 알리미의 화면. 백엔드(`backend/api`, 읽기 전용 FastAPI)의 값만 보여 주며, 하드코딩된 샘플 데이터는 없다.

- 스택: Vite + React + TypeScript. 테스트는 Vitest(+ jsdom, @testing-library/react). 라우터·상태관리·CSS 프레임워크·차트 라이브러리는 쓰지 않는다.
- 스타일은 `src/styles.css`(CSS 변수). 폰트는 Noto Sans KR(본문), Space Grotesk(D-Day 숫자)를 `index.html` 의 Google Fonts 로 불러온다.

## 실행 (프로젝트 루트에서 백엔드 먼저)

```powershell
# 1) 백엔드 (conda 환경 web_crawling). DB 는 환경변수 YOUTH_DB_PATH, 없으면 backend/data/youth.db
uvicorn backend.api.main:app --reload

# 2) 프런트엔드 (다른 터미널)
cd frontend
npm install
npm run dev        # http://localhost:5173  (/api 는 http://127.0.0.1:8000 으로 프록시)
```

| 명령 | 설명 |
|---|---|
| `npm run dev` | 개발 서버 (`/api` → `http://127.0.0.1:8000` 프록시, CORS 에 의존하지 않음) |
| `npm run build` | 타입 검사(`tsc -b`) + 프로덕션 빌드(`dist/`) |
| `npm test` | Vitest 실행 |
| `npm run lint` | oxlint |

## 구조

```
src/api/          API 클라이언트(client.ts), 응답 타입(types.ts), 요청 훅(hooks.ts: useRequest, usePagedPrograms)
src/components/   화면 조각(Header, TabBar, DeadlineView, Calendar, ChangesPanels, DetailPanel, …)
src/lib/          순수 함수(날짜·요일, 캘린더 격자·점 강도, 변경 이벤트 문구, D-Day 색 단계)
```

## 화면 규칙 요약

- D-Day 는 서버가 준 `d_day_label`·`today` 만 쓴다(브라우저 시계 사용 안 함). 요일은 날짜 문자열에서 UTC 기준으로 계산해 시간대에 따라 하루가 어긋나지 않는다.
- 탭이나 필터가 바뀌면 진행 중인 요청은 `AbortController` 로 취소해 이전 응답이 새 응답을 덮어쓰지 않는다.
- 캘린더 점은 마감 건수에 따라 3단계(1~5건 / 6~15건 / 16건 이상, 기준은 `src/lib/calendar.ts` 의 상수). 날짜 버튼의 `aria-label` 과 `title` 에도 건수를 넣는다.
- 알려진 한계는 저장소 루트의 [README.md](../README.md) 와 작업 보고를 참고.
