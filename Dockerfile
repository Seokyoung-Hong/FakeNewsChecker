FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir --disable-pip-version-check \
    "fastapi>=0.136.1" \
    "google-genai>=1.31.0" \
    "httpx>=0.28.1" \
    "hyperbrowser==0.90.8" \
    "jinja2>=3.1.6" \
    "python-dotenv>=1.1.1" \
    "python-multipart>=0.0.20" \
    "uvicorn>=0.35.0"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
