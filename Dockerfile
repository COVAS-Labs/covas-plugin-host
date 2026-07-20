FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    COVAS_PLUGINS_DIR=/app/plugins \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /uvx /bin/
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project

RUN mkdir -p /app/plugins

COPY app /app/app
COPY lib /app/lib

EXPOSE 8000

VOLUME ["/app/plugins"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
