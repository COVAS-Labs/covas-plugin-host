# COVAS Plugin Host

Standalone Docker host for COVAS:NEXT local STT/TTS plugins with an OpenAI-compatible audio API.

The image bakes in:

- Parakeet STT: `COVAS-Labs/plugin-parakeet-stt`
- Pocket TTS: `COVAS-Labs/plugin-pocket-tts`
- Gemma Embedding: `COVAS-Labs/plugin-gemma-embedding`

## Build

Install host dependencies locally with uv:

```bash
uv sync
```

Use latest plugin releases:

```bash
docker build -t covas-plugin-host .
```

Pin plugin release tags, with empty args falling back to latest:

```bash
docker build \
  --build-arg PARAKEET_VERSION=v0.0.1 \
  --build-arg POCKET_TTS_VERSION=v0.0.11 \
  --build-arg GEMMA_EMBEDDING_VERSION=v0.0.6 \
  -t covas-plugin-host .
```

## Run

```bash
docker run --rm -p 8000:8000 covas-plugin-host
```

With mounted settings:

```bash
docker run --rm -p 8000:8000 \
  -v "$PWD/settings.json:/app/settings.json:ro" \
  covas-plugin-host
```

With mounted Pocket TTS reference voices:

```bash
docker run --rm -p 8000:8000 \
  -v "$PWD/voices:/app/voices:ro" \
  covas-plugin-host
```

Then pass a voice file name without extension, for example `"voice":"selfie"` resolves to `/app/voices/selfie.wav`. Absolute paths and names with extensions are also supported by the Pocket TTS plugin.

## Settings

Defaults:

```json
{
  "stt": {
    "provider": "parakeet-stt"
  },
  "tts": {
    "provider": "pocket-tts",
    "voice": "nova",
    "response_format": "wav"
  },
  "embedding": {
    "provider": "gemma-embedding"
  },
  "plugin_settings": {
    "b7ddc677-0cfc-4081-af61-b2ebc2af5fe3": {
      "num_steps": 2,
      "max_tokens": 50,
      "inter_pass_gap_ms": 150
    }
  }
}
```

Environment overrides:

- `COVAS_SETTINGS_FILE`, default `/app/settings.json`
- `COVAS_PLUGINS_DIR`, default `/app/plugins`
- `COVAS_VOICES_DIR`, default `/app/voices`
- `COVAS_STT_PROVIDER`, default `parakeet-stt`
- `COVAS_TTS_PROVIDER`, default `pocket-tts`
- `COVAS_EMBEDDING_PROVIDER`, default `gemma-embedding`
- `COVAS_TTS_VOICE`, default `nova`
- `COVAS_TTS_RESPONSE_FORMAT`, default `wav`
- `COVAS_PLUGIN_SETTINGS_JSON`, JSON object merged into `plugin_settings`
- `COVAS_JWT_SECRET`, enables Bearer JWT verification when set

## Authentication

Authentication is disabled by default. Set `COVAS_JWT_SECRET` or `auth.jwt_secret` in `settings.json` to require Bearer JWTs for all `/v1/*` endpoints.

Tokens use HS256 by default and must include:

- `sub`: UUID subject for the token/user.
- `iat`: issued-at Unix timestamp.
- `rpm`: positive integer request limit per minute for that token.

Example token generation:

```bash
uv run python - <<'PY'
import time
import uuid
import jwt

secret = "change-me"
token = jwt.encode(
    {"sub": str(uuid.uuid4()), "iat": int(time.time()), "rpm": 60},
    secret,
    algorithm="HS256",
)
print(token)
PY
```

Authenticated request:

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer $TOKEN"
```

## API

Health:

```bash
curl http://localhost:8000/health
```

Models:

```bash
curl http://localhost:8000/v1/models
```

Transcription:

```bash
curl http://localhost:8000/v1/audio/transcriptions \
  -F model=parakeet-stt \
  -F file=@speech.wav
```

Speech synthesis streams WAV audio:

```bash
curl http://localhost:8000/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"pocket-tts","voice":"selfie","input":"Destination reached.","response_format":"wav"}' \
  --output speech.wav
```

Embeddings:

```bash
curl http://localhost:8000/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemma-embedding","input":["Elite Dangerous","COVAS plugin host"]}'
```

## Notes

Pocket TTS produces 24 kHz mono signed 16-bit PCM. The host streams that as WAV by prepending a streaming-friendly WAV header.

## Test

```bash
uv run python -m unittest discover -s tests
```
