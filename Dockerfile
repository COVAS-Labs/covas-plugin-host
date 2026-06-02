FROM python:3.12-slim

ARG PARAKEET_VERSION=""
ARG POCKET_TTS_VERSION=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    COVAS_PLUGINS_DIR=/app/plugins \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        libgomp1 \
        libsndfile1 \
        unzip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /uvx /bin/
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project

RUN mkdir -p /app/plugins /app/voices /tmp/plugin-downloads

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN download_plugin() { \
        local repo="$1"; \
        local version="$2"; \
        local asset_prefix="$3"; \
        local target_dir="$4"; \
        local api_url release_json asset_url sanitized_version; \
        if [[ -n "$version" ]]; then \
            sanitized_version="${version//./-}"; \
            api_url="https://api.github.com/repos/${repo}/releases/tags/${version}"; \
            if release_json="$(curl -fsSL "$api_url")"; then \
                asset_url="$(python -c 'import json,sys; prefix=sys.argv[1]; data=json.load(sys.stdin); assets=data.get("assets", []); matches=[a["browser_download_url"] for a in assets if a.get("name", "").startswith(prefix) and a.get("name", "").endswith("-linux.zip")]; print(matches[0] if matches else "")' "${asset_prefix}-${sanitized_version}" <<< "$release_json")"; \
            fi; \
        fi; \
        if [[ -z "$asset_url" ]]; then \
            if [[ -n "$version" ]]; then \
                echo "Pinned ${repo} release '${version}' not found or has no Linux asset; falling back to latest"; \
            fi; \
            api_url="https://api.github.com/repos/${repo}/releases/latest"; \
            release_json="$(curl -fsSL "$api_url")"; \
            asset_url="$(python -c 'import json,sys; prefix=sys.argv[1]; data=json.load(sys.stdin); assets=data.get("assets", []); matches=[a["browser_download_url"] for a in assets if a.get("name", "").startswith(prefix) and a.get("name", "").endswith("-linux.zip")]; print(matches[0] if matches else "")' "$asset_prefix" <<< "$release_json")"; \
        fi; \
        if [[ -z "$asset_url" ]]; then \
            echo "No Linux release asset found for ${repo} version '${version:-latest}'" >&2; \
            exit 1; \
        fi; \
        echo "Downloading ${asset_url}"; \
        curl -fL "$asset_url" -o "/tmp/plugin-downloads/${asset_prefix}.zip"; \
        mkdir -p "/app/plugins/${target_dir}"; \
        unzip -q "/tmp/plugin-downloads/${asset_prefix}.zip" -d "/app/plugins/${target_dir}"; \
        if [[ -f "/app/plugins/${target_dir}/requirements.txt" ]]; then \
            rm -rf "/app/plugins/${target_dir}/deps"; \
            uv pip install --python /app/.venv/bin/python --target "/app/plugins/${target_dir}/deps" -r "/app/plugins/${target_dir}/requirements.txt"; \
        fi; \
    }; \
    download_plugin "COVAS-Labs/plugin-parakeet-stt" "$PARAKEET_VERSION" "cn-plugin-parakett-stt" "cn-plugin-parakett-stt"; \
    download_plugin "COVAS-Labs/plugin-pocket-tts" "$POCKET_TTS_VERSION" "cn-plugin-pocket-tts" "cn-plugin-pocket-tts"; \
    rm -rf /tmp/plugin-downloads

COPY app /app/app
COPY lib /app/lib

EXPOSE 8000

VOLUME ["/app/voices"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
