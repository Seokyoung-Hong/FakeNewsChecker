# PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-09
**Commit:** uncommitted
**Branch:** master

## OVERVIEW
Prototype-stage FastAPI fake-news URL verification service. Current repo is spec-first: `FunctionalSpec.md` defines the target product, while implementation is still a minimal Python scaffold.

## PROJECT DEFINITION
- Product: AI-based web service that analyzes a news/SNS/blog URL and returns a 100-point trust report with rationale.
- Scope: URL input, content collection, AI analysis, scoring, report generation, result view, original content viewer.
- Exclusions: login, signup, admin, payments, complex async queues, direct OCR implementation.
- Required target runtime: future runnable code should be operated through Docker Compose; the current repo does not yet implement this.

## CURRENT STATE
- Implemented runtime today: `main.py` only; prints a placeholder message.
- Dependency state: `pyproject.toml` declares `fastapi` only.
- Missing from repo today: `app/` package, `database.py`, `models.py`, `schemas.py`, routers, services, agents, analyzers, templates, static assets, Docker Compose files, and Docker build files.
- README is empty; this file is the main operating guide until real app structure exists.

## STRUCTURE (SELECTIVE ROOT VIEW)
```text
./
├── FunctionalSpec.md   # source of truth for target product and architecture
├── main.py             # only implemented execution path today
├── pyproject.toml      # Python/FastAPI dependency metadata
├── uv.lock             # uv lockfile
├── README.md           # present but empty
└── .python-version     # local Python baseline (3.12)
```

## TARGET STRUCTURE (FROM SPEC)
```text
app/
├── main.py
├── database.py
├── models.py
├── schemas.py
├── routers/
│   ├── page.py
│   └── analysis.py
├── services/
│   ├── crawler_service.py
│   ├── analysis_service.py
│   ├── scoring_service.py
│   └── report_service.py
├── agents/
├── analyzers/
├── templates/
└── static/
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Define product scope | `FunctionalSpec.md` | Canonical source for goals, screens, API, module roles |
| Check current runnable code | `main.py` | Placeholder only; not a FastAPI app |
| Check dependency/runtime baseline | `pyproject.toml`, `.python-version`, `uv.lock` | Python 3.12 local baseline, FastAPI dependency present |
| Confirm prototype exclusions | `FunctionalSpec.md` sections 14-15 | Prevent scope creep |
| Reconstruct intended module map | `FunctionalSpec.md` sections 8-13 | Planned directories, APIs, DB schema, analyzers |

## CODE MAP
| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| `main` | function | `main.py` | 1 local call | Placeholder CLI entrypoint |

## CONVENTIONS
- Python project, not TypeScript/Node.
- Dependency management is uv-oriented (`uv.lock` present).
- Preferred local Python version is 3.12; declared support range is `>=3.11,<3.13`.
- Architecture target is a FastAPI monolith with clear internal module boundaries.
- Frontend is server-rendered HTML/CSS/JS via Jinja2; SPA frameworks are not required for this prototype.
- All future execution paths should be designed to run via Docker Compose, even though the repo does not satisfy that requirement yet.

## ANTI-PATTERNS (THIS PROJECT)
- Do not add login, signup, admin pages, payments, or other non-core product features in prototype phase.
- Do not introduce a complex async queue system for the prototype; keep request flow simple.
- Do not jump to React/Vue SPA architecture unless the product direction changes.
- Do not couple AI integration directly into page/router code; keep agent integration separable.
- Do not treat spec-only paths as implemented code; verify files exist before building on them.
- Do not add non-Docker execution as the primary target workflow; Docker Compose is the required runtime contract.

## UNIQUE STYLES
- Spec-first repository: document distinguishes sharply between current implementation and intended architecture.
- Score/report language is user-facing and evidence-oriented, not binary true/false classification.
- Trust output is a weighted 100-point model with sub-scores for source reliability, claim consistency, evidence quality, expression risk, and multimodal risk.

## COMMANDS
```bash
# currently runnable
python main.py

# required future workflow (not implemented yet)
docker compose up --build
```

## NOTES
- `docker compose up --build` is a project requirement from the user, not a capability the current repo already implements.
- There is no committed application code yet; repository is effectively an uncommitted scaffold plus specification.
- If implementation starts, create `app/` and Compose files before expanding feature modules so runtime shape stays consistent.
