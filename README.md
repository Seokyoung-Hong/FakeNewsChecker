# Fake News Verification Prototype

FastAPI + Jinja2 prototype for submitting a news/SNS/blog URL and viewing a deterministic trust-style report.

## Prototype scope

- Primary runtime path: Docker Compose only
- Supported user flow: `GET /` → `POST /analysis` → `GET /analysis/{analysis_id}`
- The analysis pipeline is a deterministic offline stub (`crawler -> analysis -> scoring -> report`)
- Results are stored in an in-memory repository inside the running web container

## What this prototype does

- Renders a homepage with a URL form
- Accepts a valid URL and redirects to a result page
- Shows a deterministic score, label, summary, five criteria blocks, and original-content viewer text
- Keeps all behavior offline and reproducible for the same input URL

## What this prototype does not do

- It does **not** perform real crawling
- It does **not** call external AI models or real fake-news detection systems
- It does **not** provide durable storage
- It does **not** track real background progress; the loading state is UI-only

## Important runtime caveat

Analysis results live only in the web process memory. If you restart or rebuild the container, previously generated `/analysis/{analysis_id}` pages are expected to disappear.

## Run the prototype

### Prerequisite

- Docker Desktop / Docker Engine with Compose support

### Start

```bash
docker compose up --build
```

### Open the app

- Homepage: `http://localhost:8000/`

### Manual verification path

1. Open the homepage.
2. Submit a valid URL such as `https://example.com/news-story`.
3. Confirm the browser redirects to `/analysis/{analysis_id}`.
4. Confirm the result page shows:
   - a numeric score out of 100
   - a score label
   - a summary report
   - five detailed criteria cards
   - an original content viewer section

### Stop

```bash
docker compose down
```

## Optional contributor sanity checks

These are useful for local diagnostics, but they are not the primary runtime path.

```bash
uv sync
python -c "import app.main; print('ok')"
python -m compileall app
```
