# UI + Backend Skeleton Implementation Plan

## TL;DR
> **Summary**: Build a Docker Compose-run FastAPI monolith that serves a server-rendered fake-news verification prototype with index/result UI, a synchronous stub analysis pipeline, and future-ready seams for crawler/agent/analyzer/persistence replacement.
> **Deliverables**:
> - FastAPI app bootstrap under `app/`
> - Jinja2 UI for index, submit-progress overlay, and result view
> - `GET /`, `POST /analysis`, `GET /analysis/{analysis_id}` flow
> - Deterministic in-memory result storage
> - Stub crawler/analysis/scoring/report pipeline and future-facing agent/analyzer/database skeletons
> - Dockerfile + `docker-compose.yml` runtime path
> **Effort**: Medium
> **Parallel**: YES - 3 waves
> **Critical Path**: 1 → 2 → 5 → 7

## Context
### Original Request
사용자 요청: 구현 계획 작성. 구현 범위는 웹페이지 UI 및 필수 백엔드 서버이며, 실제 검증 기능은 작성하지 않아도 된다. 다만 이후 실제 검증 기능을 집어넣을 수 있도록 뼈대는 갖추어야 한다.

### Interview Summary
- 범위는 웹 UI + 필수 FastAPI 서버다.
- 실제 뉴스 검증 로직, 외부 AI 연동, 실크롤링은 구현하지 않는다.
- mock 분석 흐름은 단계별 stub (`crawler → analysis → scoring → report`)로 구현한다.
- 결과 저장은 실제 DB가 아닌 in-memory 저장소로 제한한다.
- 자동 테스트는 포함하지 않고 agent-executed QA만 포함한다.
- 모든 실행 경로는 Docker Compose 기준으로 잡는다.
- 로딩 화면은 실제 백그라운드 처리 화면이 아니라, 제출 시 보이는 프런트엔드 오버레이/전환 UI로 처리한다.

### Metis Review (gaps addressed)
- 진행 상태 UI가 실제 비동기 처리처럼 오해되지 않도록 동기 처리 + 프런트엔드 오버레이로 고정했다.
- 오류 UX를 명시 범위로 포함했다: 잘못된 URL, 존재하지 않는 분석 ID, stub 처리 실패.
- in-memory 저장의 수명 경계를 명시했다: 단일 프로세스/단일 컨테이너, 재시작 시 데이터 소실.
- DB/model/schema는 미래 확장용 뼈대만 두고 런타임 핵심 경로에서는 비의존으로 유지한다.

## Work Objectives
### Core Objective
사용자가 URL을 입력하고 결과 페이지를 확인할 수 있는 FastAPI + Jinja2 프로토타입을 구현하되, 실제 검증 기능 없이도 서비스 구조와 확장 경계를 검증 가능한 수준으로 만든다.

### Deliverables
- `app/` 기반 FastAPI 애플리케이션 구조
- `GET /`, `POST /analysis`, `GET /analysis/{analysis_id}` 구현
- `templates/index.html`, `templates/result.html`, `templates/loading.html` 및 `static/css/style.css`, `static/js/main.js`
- `services/` 단계별 stub pipeline
- `agents/`, `analyzers/`, `database.py`, `models.py`, `schemas.py` 미래 확장 뼈대
- in-memory repository 및 deterministic result payload
- `Dockerfile`, `docker-compose.yml`, README 실행 안내

### Definition of Done (verifiable conditions with commands)
- `docker compose up --build`로 애플리케이션이 기동된다.
- `GET /`가 200으로 URL 입력 폼을 렌더링한다.
- `POST /analysis`가 유효한 URL 입력 시 분석 결과를 생성하고 `303` 또는 동등한 브라우저 리다이렉트로 `GET /analysis/{analysis_id}`에 도달한다.
- `GET /analysis/{analysis_id}`가 결과 점수, 라벨, 요약, 세부 항목, 원문 뷰어 영역을 렌더링한다.
- 잘못된 URL 제출과 존재하지 않는 `analysis_id` 접근 시 정의된 오류 UX를 보여준다.
- 앱은 단일 웹 컨테이너/단일 worker 전제로 동작하고, 컨테이너 재시작 후 기존 분석 결과가 사라지는 동작이 문서화된다.

### Must Have
- Thin `app/main.py` + router/service separation
- HTML form 기반 제출 플로우
- Jinja2 템플릿 + mounted static files
- deterministic stub outputs with no outbound network access
- 미래 교체 가능한 service / repository / agent / analyzer seams
- Docker Compose primary runtime

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- 실제 크롤링/실제 AI 호출/실제 검증 판정
- SQLAlchemy 기반 실DB 저장
- 로그인, 회원가입, 관리자, 결제, OCR, 비동기 큐, WebSocket, SSE
- React/Vue SPA 도입
- router 안의 비즈니스 로직/템플릿 전용 dict 남용
- 다중 worker 또는 멀티 인스턴스 전제 설계

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: none (user chose no automated tests)
- QA policy: Every task includes agent-executed scenarios only
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.

Wave 1: foundation/runtime (`1`, `2`, `3`)
Wave 2: UI shell + stub pipeline (`4`, `6`)
Wave 3: submission/result/error/docs integration (`5`, `7`, `8`)

### Dependency Matrix (full, all tasks)
| Task | Depends On | Blocks |
|------|------------|--------|
| 1 | - | 4,5,6,7 |
| 2 | 1 | 8, F3 |
| 3 | 1 | 5,6,7 |
| 4 | 1 | 5,7 |
| 5 | 1,3,4,6 | 7,8, F3 |
| 6 | 1,3 | 5,7 |
| 7 | 3,4,5,6 | 8, F3 |
| 8 | 2,5,7 | F3 |

### Agent Dispatch Summary
| Wave | Task Count | Recommended Categories |
|------|------------|------------------------|
| 1 | 3 | quick, unspecified-low |
| 2 | 2 | visual-engineering, unspecified-low |
| 3 | 3 | unspecified-high, writing, visual-engineering |

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Bootstrap the FastAPI application package and dependency wiring

  **What to do**: Replace root placeholder runtime with an `app/` package and move the real entrypoint to `app/main.py`. Add `app/__init__.py`, `app/routers/__init__.py`, `app/services/__init__.py`, `app/agents/__init__.py`, `app/analyzers/__init__.py`, and a shared `app/dependencies.py`. Update `pyproject.toml` so runtime dependencies support FastAPI HTML form flow and templating (`uvicorn`, `jinja2`, `python-multipart`) while keeping the stack minimal. Keep `main.py` at repo root only as a compatibility shim or remove it if the runtime contract is fully transferred to `app.main:app` and Docker Compose docs.
  **Must NOT do**: Do not add pytest, SQLAlchemy runtime wiring, Celery, background workers, or any external analysis SDK. Do not place business logic in `app/main.py`.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: mostly structural bootstrap and dependency declaration.
  - Skills: `[]` - no special skill required.
  - Omitted: `['review-work']` - verification happens in final wave, not during implementation.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 4,5,6,7 | Blocked By: none

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `FunctionalSpec.md:161-193` - backend/frontend stack and Jinja2 requirement.
  - Pattern: `FunctionalSpec.md:197-228` - FastAPI monolith and separated AI integration direction.
  - Pattern: `FunctionalSpec.md:238-272` - target directory/file structure.
  - Pattern: `AGENTS.md:68-82` - project conventions, Docker Compose runtime contract, anti-patterns.
  - External: `https://github.com/fastapi/fastapi/blob/622b6356b5102113d0074083ac23c82367f4284b/docs/en/docs/tutorial/bigger-applications.md` - bigger application router/package pattern.
  - External: `https://github.com/fastapi/fastapi/blob/622b6356b5102113d0074083ac23c82367f4284b/docs/en/docs/tutorial/dependencies/index.md` - dependency seams for shared services.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pyproject.toml` contains runtime dependencies required for FastAPI + Jinja2 form handling.
  - [ ] `app/main.py` defines the application bootstrap and imports cleanly under language diagnostics.
  - [ ] Package init files exist so `app.*` imports resolve cleanly.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: App package imports cleanly
    Tool: Bash
    Steps: Run `python -c "import app.main; print('ok')"` inside the compose-ready workspace or container image context.
    Expected: Command exits 0 and prints `ok`.
    Evidence: .sisyphus/evidence/task-1-bootstrap-import.txt

  Scenario: Missing dependency regression is caught
    Tool: Bash
    Steps: Run `python -c "from fastapi.templating import Jinja2Templates; import multipart; print('deps-ok')"` after dependency sync/build.
    Expected: Command exits 0 and prints `deps-ok`; if a dependency is missing the task is not complete.
    Evidence: .sisyphus/evidence/task-1-bootstrap-deps.txt
  ```

  **Commit**: NO | Message: `feat(app): bootstrap FastAPI package` | Files: `pyproject.toml`, `app/**`, optional `main.py`

- [x] 2. Add Docker runtime files and lock the single-container execution model

  **What to do**: Create `Dockerfile`, `docker-compose.yml`, and `.dockerignore` so the primary documented run path is `docker compose up --build`. Use a single web service only. Ensure the compose service starts the FastAPI app with one worker and exposes the documented port. If a root `main.py` remains, it must not be the primary runtime path in Docker.
  **Must NOT do**: Do not introduce a database container, Redis, worker container, hot-reload-dependent production command, or multi-worker Uvicorn/Gunicorn setup.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` - Reason: small runtime/ops file creation with some architectural guardrails.
  - Skills: `[]` - no external deployment skill needed.
  - Omitted: `['microsoft-foundry']` - unrelated to local Docker Compose runtime.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 8, F3 | Blocked By: 1

  **References**:
  - Pattern: `AGENTS.md:89-101` - primary runtime target is Docker Compose, currently unimplemented.
  - Pattern: `FunctionalSpec.md:167-171` - FastAPI + Uvicorn stack.
  - Pattern: `FunctionalSpec.md:223-224` - single project, not distributed architecture.

  **Acceptance Criteria**:
  - [ ] `docker compose up --build` starts exactly one web application service.
  - [ ] The compose service launches the FastAPI app from `app.main:app` (or an equivalent app package path), not the placeholder root script.
  - [ ] Restart semantics are documented: in-memory results are lost on container restart.

  **QA Scenarios**:
  ```
  Scenario: Compose runtime boots
    Tool: Bash
    Steps: Run `docker compose up --build -d` and then `docker compose ps`.
    Expected: One web service is `running`/`healthy` on the documented port.
    Evidence: .sisyphus/evidence/task-2-compose-ps.txt

  Scenario: Restart wipes in-memory state by design
    Tool: Bash
    Steps: After a result exists, run `docker compose restart web` (or the actual service name), then request the previously generated `/analysis/{analysis_id}` URL.
    Expected: Previously stored result is no longer available and the app returns the defined not-found behavior.
    Evidence: .sisyphus/evidence/task-2-compose-restart.txt
  ```

  **Commit**: NO | Message: `build(docker): add compose runtime` | Files: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, optional README edits

- [x] 3. Define shared DTOs, in-memory repository, and future-facing persistence skeletons

  **What to do**: Create `app/schemas.py` with typed request/result/view models or split submodules if preferred, but keep the public contracts explicit. Add an in-memory repository abstraction that can create and fetch analysis results by ID. Create `app/database.py` and `app/models.py` as future-facing placeholders only; they must not be required for live request handling. Define deterministic payload structures for crawler output, analysis output, scoring output, and report output so services exchange typed objects instead of template-shaped dicts.
  **Must NOT do**: Do not wire SQLAlchemy sessions, migrations, actual tables, or disk persistence. Do not let templates or routers own repository storage shape.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` - Reason: shared contracts and storage seam design.
  - Skills: `[]` - internal type modeling only.
  - Omitted: `['refactor']` - greenfield skeleton, not a refactor.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 5,6,7 | Blocked By: 1

  **References**:
  - Pattern: `FunctionalSpec.md:431-445` - `AnalysisResult` fields expected in persistence.
  - Pattern: `FunctionalSpec.md:402-426` - representative analysis output keys.
  - Pattern: `FunctionalSpec.md:137-157` - score bands and detail sections required for result rendering.
  - Pattern: `FunctionalSpec.md:502-526` - analyzer contract direction.
  - External: `https://github.com/fastapi/fastapi/blob/622b6356b5102113d0074083ac23c82367f4284b/docs/en/docs/tutorial/dependencies/classes-as-dependencies.md` - dependency-driven service/repository seam pattern.

  **Acceptance Criteria**:
  - [ ] Typed contracts exist for URL submission input, rendered result payload, and internal stage outputs.
  - [ ] In-memory repository supports create/get by `analysis_id` with deterministic IDs or UUID generation.
  - [ ] `database.py` and `models.py` are import-safe placeholders and are not invoked by the live route path.

  **QA Scenarios**:
  ```
  Scenario: Repository create/get contract works
    Tool: Bash
    Steps: Run a small Python snippet that constructs the repository, stores one fake result, and fetches it by ID.
    Expected: Fetched object matches the stored ID and contains score, label, summary, details, and original content fields.
    Evidence: .sisyphus/evidence/task-3-repository.txt

  Scenario: Placeholder DB modules do not hijack runtime
    Tool: Bash
    Steps: Run `python -c "import app.database, app.models, app.schemas; print('placeholder-ok')"`.
    Expected: Command exits 0 and prints `placeholder-ok` without requiring DB env vars or DB connections.
    Evidence: .sisyphus/evidence/task-3-placeholders.txt
  ```

  **Commit**: NO | Message: `feat(domain): add DTOs and in-memory repository` | Files: `app/schemas.py`, `app/database.py`, `app/models.py`, repository module(s)

- [x] 4. Build the page router and base HTML shell for the submission experience

  **What to do**: Implement the page router responsible for `GET /` and base template wiring. Create `templates/index.html` plus a reusable loading/progress UI representation that is shown as a client-side submission overlay or include. The index page must contain the product headline, URL input, validation/error surface, example/help text, and a visible “analysis in progress” step list that can be activated by frontend JS on submit without pretending to reflect real backend progress.
  **Must NOT do**: Do not add extra backend routes for fake progress, polling, WebSocket, or SSE. Do not let index rendering depend on live analysis services.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: HTML/CSS layout and UX clarity are central here.
  - Skills: `[]` - direct templating work only.
  - Omitted: `['frontend-ui-ux']` - optional but unnecessary unless UI quality becomes the dominant concern.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 5,7 | Blocked By: 1

  **References**:
  - Pattern: `FunctionalSpec.md:37-70` - main screen purpose, UI contents, and simple ChatGPT-style central input direction.
  - Pattern: `FunctionalSpec.md:73-100` - progress step labels to mirror in the overlay.
  - External: `https://github.com/fastapi/fastapi/blob/622b6356b5102113d0074083ac23c82367f4284b/docs/en/docs/advanced/templates.md`
  - External: `https://github.com/fastapi/fastapi/blob/622b6356b5102113d0074083ac23c82367f4284b/docs/en/docs/tutorial/static-files.md`

  **Acceptance Criteria**:
  - [ ] `GET /` renders a form with a URL field, submit button, and helper text.
  - [ ] The page includes a progress UI with the four spec steps but treats it as client-side presentation only.
  - [ ] Static CSS/JS references resolve correctly through the mounted static path.

  **QA Scenarios**:
  ```
  Scenario: Homepage renders submission UI
    Tool: Playwright
    Steps: Open `http://localhost:8000/`; assert visible text for the headline, one URL input, and one submit button.
    Expected: Page shows the submission form and no server error.
    Evidence: .sisyphus/evidence/task-4-homepage.png

  Scenario: Submit overlay appears without extra backend route
    Tool: Playwright
    Steps: Fill the URL field with `https://example.com/news/demo`; click submit; capture the immediate DOM state before navigation completes.
    Expected: A visible loading/progress overlay or state appears showing the four analysis steps; no `/loading` backend route is requested.
    Evidence: .sisyphus/evidence/task-4-overlay.png
  ```

  **Commit**: NO | Message: `feat(ui): add homepage and loading overlay shell` | Files: `app/routers/page.py`, `templates/index.html`, `templates/loading.html`, base template(s), static assets

- [x] 5. Implement the analysis submission route, validation behavior, and redirect contract

  **What to do**: Implement `POST /analysis` in the analysis router. It must accept browser form submission, validate URL input, call the stub orchestration service, store the result in the in-memory repository, and finish with an HTTP redirect to `GET /analysis/{analysis_id}` using `303` or an equivalent browser-safe redirect status. Define the invalid input UX now: return the index page with an inline error message and preserved input rather than a generic JSON error. Define the internal stub failure UX now: return a controlled error state/page with a readable retry path.
  **Must NOT do**: Do not return raw JSON as the main happy-path browser response. Do not call external networks. Do not create a fake backend loading route.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: HTTP flow, validation, and UX error handling all meet here.
  - Skills: `[]` - standard FastAPI form/redirect work.
  - Omitted: `['playwright']` - browser QA belongs in scenario execution, not implementation instructions.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: 7,8, F3 | Blocked By: 1,3,4,6

  **References**:
  - Pattern: `FunctionalSpec.md:462-486` - required `POST /analysis` flow.
  - Pattern: `FunctionalSpec.md:57-65` - URL validation and API request expectations.
  - Pattern: `FunctionalSpec.md:98-100` - avoid complex async queue system.
  - External: `https://github.com/fastapi/fastapi/blob/622b6356b5102113d0074083ac23c82367f4284b/docs/en/docs/tutorial/request-form-models.md`

  **Acceptance Criteria**:
  - [ ] Valid URL form submission results in a stored analysis record and redirects to `/analysis/{analysis_id}`.
  - [ ] Invalid URL submission re-renders the input screen with a visible inline error.
  - [ ] Stub processing failure returns a controlled error state with a visible retry path.

  **QA Scenarios**:
  ```
  Scenario: Valid URL redirects to result page
    Tool: Playwright
    Steps: Open `/`; fill `https://example.com/news/demo`; submit the form; wait for navigation.
    Expected: Browser lands on `/analysis/<id>`; response is successful; page is not blank or JSON.
    Evidence: .sisyphus/evidence/task-5-valid-submit.png

  Scenario: Invalid URL shows inline validation error
    Tool: Playwright
    Steps: Open `/`; fill `not-a-url`; submit the form.
    Expected: Browser remains on the submission page (or equivalent error state) and shows a visible inline error message near the form.
    Evidence: .sisyphus/evidence/task-5-invalid-submit.png
  ```

  **Commit**: NO | Message: `feat(api): add form submission and redirect flow` | Files: `app/routers/analysis.py`, form schema(s), template error binding

- [x] 6. Implement the deterministic stub pipeline and pluggable service seams

  **What to do**: Implement `crawler_service.py`, `analysis_service.py`, `scoring_service.py`, and `report_service.py` so they exchange explicit DTOs and produce deterministic outputs. Implement `agents/base.py`, `agents/local_agent.py`, `agents/external_agent_client.py`, `analyzers/base.py`, `analyzers/source_analyzer.py`, `analyzers/claim_analyzer.py`, `analyzers/expression_analyzer.py`, and `analyzers/multimodal_analyzer.py` as interfaces or fake implementations only. Use a dependency provider in `app/dependencies.py` so routers depend on an orchestration service rather than concrete classes. The stub pipeline must not fetch the submitted URL or perform network I/O; it may synthesize original-content text and analysis details from deterministic placeholder logic.
  **Must NOT do**: Do not perform outbound HTTP requests, hidden retries, random scoring, or route-level business logic. Do not leak FastAPI `Request` objects into services.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` - Reason: most work is deterministic skeleton service design.
  - Skills: `[]` - no specialist required.
  - Omitted: `['oracle']` - architecture decisions are already fixed in this plan.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 5,7 | Blocked By: 1,3

  **References**:
  - Pattern: `FunctionalSpec.md:277-381` - required roles for crawler/analysis/scoring/report services.
  - Pattern: `FunctionalSpec.md:385-426` - analysis request/response shape expectations.
  - Pattern: `FunctionalSpec.md:502-526` - analyzer abstraction model.
  - External: `https://github.com/fastapi/fastapi/blob/622b6356b5102113d0074083ac23c82367f4284b/docs/en/docs/tutorial/dependencies/index.md`
  - External: `https://github.com/fastapi/fastapi/blob/622b6356b5102113d0074083ac23c82367f4284b/docs/en/docs/tutorial/dependencies/classes-as-dependencies.md`

  **Acceptance Criteria**:
  - [ ] Service stages are separated and produce deterministic outputs for the same input.
  - [ ] A dependency provider returns the active analysis/orchestration service implementation.
  - [ ] No service issues real network requests or requires secrets/config for startup.

  **QA Scenarios**:
  ```
  Scenario: Stub pipeline output is deterministic
    Tool: Bash
    Steps: Run a Python snippet that invokes the orchestration service twice with `https://example.com/news/demo`.
    Expected: Both runs produce the same score, label, detail keys, and original content stub fields.
    Evidence: .sisyphus/evidence/task-6-deterministic.txt

  Scenario: No outbound network call path exists in happy path
    Tool: Bash
    Steps: Search implementation files for live HTTP client usage in active stub path (`requests`, `httpx`, `aiohttp`) and run the service invocation offline if possible.
    Expected: Active pipeline completes without any external request dependency.
    Evidence: .sisyphus/evidence/task-6-offline.txt
  ```

  **Commit**: NO | Message: `feat(services): add deterministic analysis skeleton` | Files: `app/services/**`, `app/agents/**`, `app/analyzers/**`, `app/dependencies.py`

- [x] 7. Render the result page, score bands, and original content viewer from stored results

  **What to do**: Implement `GET /analysis/{analysis_id}` in the page router and create `templates/result.html` so the stored result is rendered as a human-readable report. The page must show the overall trust score, score band label, summary report text, detailed analysis sections for the five criteria, and an original content viewer area populated from stub crawler output. Define the unknown-ID behavior now: return a dedicated not-found page/state with clear navigation back to `/` and an HTTP 404 status.
  **Must NOT do**: Do not embed raw JSON blobs directly into the page as the primary presentation. Do not hide missing-ID failures behind a generic 500.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: result presentation and not-found UX are mostly UI work on top of existing contracts.
  - Skills: `[]` - server-rendered UI only.
  - Omitted: `['dev-browser']` - interactive browser automation is for QA, not plan execution.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: 8, F3 | Blocked By: 3,4,5,6

  **References**:
  - Pattern: `FunctionalSpec.md:104-131` - result screen fields.
  - Pattern: `FunctionalSpec.md:137-157` - score bands and detailed criteria.
  - Pattern: `FunctionalSpec.md:490-498` - `GET /analysis/{analysis_id}` requirement.
  - Pattern: `FunctionalSpec.md:433-444` - minimum persisted fields.

  **Acceptance Criteria**:
  - [ ] Existing `analysis_id` renders a 200 result page with all required sections.
  - [ ] Unknown `analysis_id` renders a defined 404 UX with a return path.
  - [ ] Result page maps score ranges to the specified label bands.

  **QA Scenarios**:
  ```
  Scenario: Result page shows all report sections
    Tool: Playwright
    Steps: Create one result through the form, then assert the result page shows a numeric score, band label, summary text, five detailed criteria blocks, and an original content viewer section.
    Expected: All sections are visible and populated with deterministic stub content.
    Evidence: .sisyphus/evidence/task-7-result-page.png

  Scenario: Unknown ID returns not-found UX
    Tool: Playwright
    Steps: Open `http://localhost:8000/analysis/does-not-exist`.
    Expected: HTTP 404 or equivalent browser-visible not-found state is rendered with a link/button back to `/`.
    Evidence: .sisyphus/evidence/task-7-not-found.png
  ```

  **Commit**: NO | Message: `feat(ui): render analysis results and not-found state` | Files: `app/routers/page.py`, `templates/result.html`, optional `templates/404.html`, static assets

- [x] 8. Finish operational docs, diagnostics cleanup, and Compose-first manual verification path

  **What to do**: Update `README.md` so the primary runbook documents only the supported prototype flow: dependency sync if needed, `docker compose up --build`, how to access the app, what the stub pipeline does and does not do, and the restart data-loss caveat. Run language diagnostics/build sanity checks and remove dead imports or broken template/static references. Ensure the documented commands and actual runtime behavior match.
  **Must NOT do**: Do not document unsupported local-first workflows as the primary path. Do not claim persistence, real verification, or background progress.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: this is documentation and operational clarity work with some cleanup.
  - Skills: `[]` - plain technical writing.
  - Omitted: `['init-deep']` - AGENTS generation is already complete and out of scope.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: F3 | Blocked By: 2,5,7

  **References**:
  - Pattern: `AGENTS.md:89-101` - current command/runtime caveats that must be superseded by real docs.
  - Pattern: `FunctionalSpec.md:530-568` - in/out of scope and design principles to restate clearly.
  - Pattern: `FunctionalSpec.md:572-574` - final product definition for README summary.

  **Acceptance Criteria**:
  - [ ] README documents Docker Compose as the primary runtime path.
  - [ ] README explicitly states that analysis results are deterministic stubs and that in-memory storage is cleared on restart.
  - [ ] Diagnostics/build sanity checks pass with no unresolved imports in the implemented app path.

  **QA Scenarios**:
  ```
  Scenario: README runbook matches actual runtime
    Tool: Bash
    Steps: Follow only the README-documented commands from a clean terminal session.
    Expected: The documented flow starts the app and the homepage loads as described.
    Evidence: .sisyphus/evidence/task-8-readme-runbook.txt

  Scenario: Diagnostics catch broken app wiring
    Tool: Bash
    Steps: Run the project's chosen import/runtime sanity checks and `lsp_diagnostics` on `app/` after implementation.
    Expected: No unresolved import or syntax errors remain in the live app path.
    Evidence: .sisyphus/evidence/task-8-diagnostics.txt
  ```

  **Commit**: NO | Message: `docs(readme): document compose-first prototype flow` | Files: `README.md`, optional minor cleanup across app/runtime files

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- Prefer one final implementation commit after F1-F4 approval.
- Suggested commit message: `feat(app): add docker-compose FastAPI UI skeleton for analysis flow`
- Do not create intermediate commits unless implementation branch policy requires checkpoints.

## Success Criteria
- Prototype is runnable only through Docker Compose as primary documented path.
- Core user flow works end-to-end with deterministic stub data.
- Extension seams exist for future real verification work without refactoring routers/templates.
- No out-of-scope production logic or persistence complexity is introduced.
