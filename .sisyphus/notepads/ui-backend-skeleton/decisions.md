## Task 1 decisions

- Keep `app/main.py` strictly as a bootstrap module (`create_app()` + `app`) with no feature routes.
- Keep compatibility packages in place with empty package `__init__.py` files to satisfy import-safe skeleton expansion in later tasks.
- Keep `app/dependencies.py` minimal and safe (`get_templates`) without touching runtime logic.
- Add ASGI/template/form dependencies in `pyproject.toml` only, and avoid importing optional runtime launcher code in `app/main.py` so diagnostics remain clean in a minimal environment.

- Lock runtime to a single web service and one worker in compose (`web` service only, `uvicorn ... --workers 1`) to enforce single-container, single-worker execution model from task 2A/2B.
- Use `.dockerignore` to keep build context lean and avoid committing local venv/git artifacts into images.

- Kept database persistence as placeholders only: pp/database.py and pp/models.py are import-safe and avoid creating DB sessions or engine dependencies; repository contract uses a minimal protocol/implementation to support seam-first design while avoiding live storage assumptions.

- (clarification) Kept database persistence modules as placeholders only: pp/database.py and pp/models.py stay import-safe and avoid real DB setup; repository remains an in-memory seam pending task 6 integration.

- Decision: Keep database/model modules as placeholders (`app/database.py`, `app/models.py`) and keep persistence through in-memory repository for this prototype task.

- Task 4 decision: mount `/static` in `app.main` and keep `app/routers/page.py` limited to a single `GET /` Jinja render so page delivery stays thin and later submission logic can land without reworking bootstrap structure.

- Task 5 decision: keep `POST /analysis` in a dedicated analysis router, but add only a minimal HTML `GET /analysis/{analysis_id}` target there for redirect verification so task 7 can still own the full result-page rendering later.

- Task 5 decision: route invalid form submissions back through `GET /` query parameters instead of rendering the homepage directly from the POST response, because that keeps the browser on the homepage URL while preserving inline error state and submitted input.

- Task 7 decision: reuse `analysis_error.html` for the unknown-analysis `404` state instead of adding a dedicated not-found template, keeping the scope limited to real result rendering while still providing a clear return path to `/`.

- Task 7 decision: keep the result page in a dedicated `result.html` template and limit router changes to repository lookup plus template selection, so presentation stays in Jinja/CSS rather than inline HTML in the route.

- Task 8 decision: keep README operational guidance centered on Docker Compose and treat local `uv sync` / import / compile commands as contributor-only sanity checks, not as an alternative supported runtime path.

- Task 8 decision: clean diagnostics noise in the live app path with typed stub-class attributes and file-level implicit-override suppression only, avoiding behavioral changes or broader refactors this late in the plan.
\n- Decision: Keep evidence criterion generation as an internal service fallback via LocalAgent (no dedicated EvidenceAnalyzer file) after comparing FunctionalSpec structure, which only prescribes four analyzer modules and uses criteria dictionary output including evidence_quality.\n
