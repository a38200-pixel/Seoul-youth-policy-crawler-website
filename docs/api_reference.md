# API Reference

읽기 전용 백엔드(FastAPI)의 엔드포인트입니다. 근거는 `backend/api/main.py` 와 `backend/api/queries.py` 입니다. 모두 **GET** 이며 쓰기 엔드포인트는 없습니다(6개).

- 실행: 프로젝트 루트에서 `uvicorn backend.api.main:app --reload` → http://127.0.0.1:8000 (자동 문서: `/docs`)
- DB 는 요청마다 읽기 전용(`mode=ro`)으로 열고 닫습니다. DB 경로는 환경변수 `YOUTH_DB_PATH`, 기본값 `backend/data/youth.db`. DB 파일이 없거나 열 수 없으면 DB 를 만들지 않고 **503** 을 돌려줍니다.
- "오늘"은 Asia/Seoul 날짜입니다(테스트에서는 `get_today` 의존성으로 고정).
- 표시 계산(D-Day·그룹·정렬·배지)은 `backend/service/display.py` 의 함수를 그대로 씁니다.
- CORS: `http://localhost:5173`, `http://127.0.0.1:5173` 에서 오는 GET 만 허용합니다. 인증은 없습니다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/health` | 상태 확인 |
| GET | `/api/meta` | 오늘 날짜, 건수, 분야 목록, 마지막 수집 시각 등 |
| GET | `/api/programs` | 활성 공고 목록 |
| GET | `/api/calendar` | 월별 마감 달력 |
| GET | `/api/programs/{source_id}` | 공고 상세와 변경 이력 |
| GET | `/api/changes` | 최근 변경 목록 |

## GET /api/health

응답: `{"status": "ok", "db_available": true|false}`. DB 를 열거나 만들지 않고 파일이 있는지만 확인합니다.

## GET /api/meta

응답 필드: `today`, `active_count`, `expired_active_count`(활성이지만 마감이 지나 목록에서 빠지는 행), `tab_counts`(`deadline`, `always`, `etc`, `all`), `categories`(`[{name, count}]`, 건수 내림차순·같으면 이름 순), `last_collected_at`(활성 행의 `last_seen_at` 최댓값, 없으면 null), `window_days`(7), `events_7d`(최근 7일 변경 종류별 건수), `new_7d`, `baseline_date`.

## GET /api/programs

| 쿼리 | 값 | 설명 |
|---|---|---|
| `tab` | `deadline`(기본) / `always` / `etc` / `all` | `deadline`: 모집중+모집예정+마감일 미정, `always`: 상시(분야 있음), `etc`: 상시-기타(분야 없음), `all`: 확인 필요 포함·마감 지난 공고 제외 |
| `q` | 문자열 | 제목·기관·분야 부분 일치 |
| `category` | 문자열 | 분야 정확히 일치 |
| `group` | `recruiting` / `upcoming` / `open` / `always` / `always_etc` / `unknown` | 표시 그룹 필터. 그 밖의 값은 422 |
| `date` | `YYYY-MM-DD` | 마감일이 그 날짜인 공고만. 형식이 틀리면 422 |
| `limit` | 1~200 (기본 50) | 범위를 벗어나면 422 |
| `offset` | 0 이상 (기본 0) | |

응답: `{items, total, counts, group_counts}`.
- `total`: 탭·`date`·`group` 필터를 적용한 건수.
- `counts`(`deadline`, `always`, `etc`)와 `group_counts`(그룹 6종): `q`·`category` 만 적용한 건수이고, 탭·`date`·`group` 과는 무관합니다. 마감 지난 공고는 제외됩니다.
- 정렬은 표시 규칙의 순서(모집중 D-Day 순 → 모집예정 → 마감일 미정 → 상시 → 상시-기타 → 확인 필요)이며 정렬한 뒤에 `limit`/`offset` 을 적용합니다.

`items` 한 건의 필드: `source_id`, `title`, `category`, `organization`, `display_status`, `group`, `d_day`, `d_day_label`, `source_status`(사이트가 표시한 모집상태 그대로), `period_text`, `start_date`, `end_date`, `apply_url`, `source_url`, `first_seen_at`, `badges`, `calendar_exportable`.

`calendar_exportable` 은 활성이고, 그룹이 모집중 또는 모집예정이고, 마감일이 있고, 마감일이 오늘(서울) 이후인 공고에서만 true 입니다.

## GET /api/calendar

| 쿼리 | 값 | 설명 |
|---|---|---|
| `month` | `YYYY-MM` (필수) | 형식이 틀리거나 연도가 2000~2100 밖이면 422 |
| `q`, `category` | | `/api/programs` 와 같은 의미 |

응답: `{month, today, days: [{date, count}]}`. 그 달에 마감일이 있는 모집중·모집예정 공고만 세며, 건수가 1 이상인 날짜만 날짜 오름차순으로 돌려줍니다. 같은 필터에서 `/api/programs?date=X` 의 `total` 과 이 응답의 X 날짜 `count` 는 같아야 하고, 테스트로 고정했습니다(같은 판정 함수 `display.deadline_on` 사용).

## GET /api/programs/{source_id}

목록 항목의 모든 필드에 `summary`, `target`, `schedule_text`, `is_active`, `history` 가 더해집니다. `history` 는 변경 이력(최신순)이며 항목은 `id`, `change_type`, `old_value`, `new_value`, `reason`, `detected_at` 입니다.

- 없는 `source_id` 는 404 입니다.
- 비활성 행도 200 이며 `is_active` 는 false, `display_status` 는 `비활성`, D-Day 는 없습니다.

## GET /api/changes

| 쿼리 | 값 | 설명 |
|---|---|---|
| `days` | 1~90 (기본 7) | 최근 N일 |
| `type` | `new` / `extended` / `shortened` / `period_changed` / `status_changed` / `deactivated` / `reactivated` | 선택. 그 밖의 값은 422 |

응답: `{days, total, counts, items}`. `counts` 는 `type` 필터와 무관한 종류별 건수입니다. 시각 내림차순입니다.

`items` 한 건의 필드: `id`(NEW 는 null), `type`, `source_id`, `title`, `detected_at`, `old_value`, `new_value`, `reason`, `end_date`, `period_type`. `end_date`·`period_type` 은 공고 행이 없으면 null 입니다.

- `new` 는 변경 이벤트 행이 아니라 `first_seen_at` 으로 계산한 값입니다(활성 행만, `detected_at` 은 `first_seen_at`). 기준일(2026-10-01)에 처음 적재한 행은 NEW 가 아닙니다.
- `deactivated` 의 `reason` 은 `expired`(마감일이 있고 그 날짜가 수집일보다 이름) / `early`(그 외)입니다. 이 값은 사이트가 알려 준 이유가 아니라 마감일과 사라진 시점을 비교해 **계산한 값**입니다.
