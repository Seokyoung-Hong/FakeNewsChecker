## Task 1 (Bootstrap) learnings

- Minimal runtime scaffolding for task 1 is small: `pyproject.toml` + `app/` package init files + `app/main.py`.
- `python-multipart` and `jinja2` are required for form handling plus templating imports expected by the spec.
- Adding `uvicorn` dependency enables ASGI runtime, while keeping `app.main` free of any route/business logic preserves a thin bootstrap.
- `lsp_diagnostics` is useful before calling task complete; it caught a false-positive risk from a `uvicorn` import in `if __name__ == "__main__"`.

- Added Docker runtime files with minimal single-container configuration (`Dockerfile`, `.dockerignore`, `docker-compose.yml`) and confirmed compose can build and start the `app.main:app` ASGI app on port `8000`.

- Task 3 DTO/repository skeleton added typed contracts in pp/schemas.py covering URL submission, crawler, analysis, scoring, report, and final result payload; added InMemoryAnalysisResultRepository for deterministic create/get by analysis_id in pp/repositories.py.

- (clarification) Task 3 DTO/repository skeleton added typed contracts in pp/schemas.py and in-memory create/get in pp/repositories.py for URL submission, crawler, analysis, scoring, report, and final result payloads.

- Task 3 clarification: Appended typed contracts in `app/schemas.py` and in-memory repository in `app/repositories.py` for submission input, internal pipeline stages, and final rendered result payloads.

- Task 4 kept homepage behavior intentionally client-only: `GET /` renders the centered form and JS activates the loading shell locally so the UI can demonstrate the future submission flow without adding `POST /analysis` or a fake `/loading` endpoint early.

- Task 4 favicon follow-up: adding `<link rel="icon" href="data:,">` in `app/templates/index.html` suppresses the browser's default `/favicon.ico` request without changing the loading overlay or submission flow.

- Task 5 learning: `POST /analysis` can keep browser-safe UX simple by using a 303 redirect on both branches—valid submissions go to `/analysis/{analysis_id}`, while invalid submissions bounce back to `/?url=...&error=...` so the homepage can preserve the typed value and show an inline server-defined error.

- Task 5 verification note: the homepage submit overlay still works without a fake loading route by showing only on client-side valid submits and letting the browser perform the real form POST immediately after.

- Task 5 follow-up: when the browser navigates too quickly to show the loading overlay, a minimal `requestAnimationFrame()` + short `setTimeout()` delay before `form.requestSubmit()` is enough to make the overlay observable while preserving the real POST and redirect flow.

- F3 follow-up: for more reliable overlay visibility across fast browser timing paths, forcing a layout flush after toggling the overlay and waiting through two animation frames before `requestSubmit()` gave the browser enough time to paint the visible state before leaving `/`.
\n- Task 6A/6B completion check: running get_active_analysis_service() twice with the same URLSubmission(url='https://example.com/news/story-1?a=1') produced identical nalysis_id, score, label, summary, and all per-criterion ReportDetail fields; result includes 5 details in deterministic order.\n

- 2026-05-09 browser re-check: valid submit showed #loading-overlay before navigation (aria-hidden true->false, visibility hidden->visible) and completed at /analysis/8cbcaa3f-6e9d-5678-975f-a391801c2197; invalid submit stayed on homepage with inline error '올바른 URL 형식으로 입력해 주세요.'; console errors: none.

- Task 7 learning: `GET /analysis/{analysis_id}` can stay thin by fetching the stored `AnalysisResult` from the repository and passing the full object directly into Jinja, which is enough to render score, label, summary, five criteria, and the original content viewer without new DTO reshaping in the route.

- Task 7 verification: after rebuilding compose, `POST /analysis` returned `303` to a stored `/analysis/{analysis_id}` page whose HTML contained the score badge, a recognized band label, the summary section, all five criteria labels, and the original content viewer; requesting an unknown ID returned `404` with the not-found title and a link back to `/`.

- Task 8 learning: the README should document only the Compose-first prototype path (`docker compose up --build`) and explicitly warn that the current analysis pipeline is deterministic offline stub logic, not real fake-news detection.

- Task 8 verification: `python -c "import app.main; print('ok')"`, `python -m compileall app`, and `lsp_diagnostics` on `app/` all passed after the targeted annotation cleanup; `docker compose up --build -d` served `GET /` with HTTP 200, `POST /analysis` returned `303` to `/analysis/{analysis_id}`, and the redirected result page rendered the expected core sections.
