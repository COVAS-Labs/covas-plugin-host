# COVAS Plugin Host

Standalone Docker host for COVAS:NEXT plugins with an OpenAI-compatible audio API. The image starts only the host service; it does not include, download, install, or configure any plugins.

## Run

Pull the published image:

```bash
docker pull ghcr.io/covas-labs/covas-plugin-host:latest
```

Mount a plugin directory and a settings file that selects its providers:

```bash
docker run --rm -p 8000:8000 \
  -v "$PWD/plugins:/app/plugins:ro" \
  -v "$PWD/settings.json:/app/settings.json:ro" \
  ghcr.io/covas-labs/covas-plugin-host:latest
```

The mounted directory must contain one directory per plugin, each with a `manifest.json`, its Python entrypoint, models, and a `deps/` directory containing its Python dependencies. Plugin artifacts must be compatible with the image platform (`linux/amd64` or `linux/arm64`). The host does not run plugin installers.

Example layout:

```text
plugins/
  your-stt-plugin/
    manifest.json
    plugin.py
    deps/
    model/
  your-tts-plugin/
    manifest.json
    plugin.py
    deps/
```

An empty or absent plugin directory is valid: the host starts and reports no models. Mount the directory at a different path with `COVAS_PLUGINS_DIR` if required.

## Development

Build the image locally only when developing the host:

```bash
uv sync
docker build -t covas-plugin-host .
```

## Settings

The host selects no providers by default. Configure the plugin provider IDs and any plugin-specific settings in `settings.json`:

```json
{
  "stt": { "provider": "your-stt-provider" },
  "tts": {
    "provider": "your-tts-provider",
    "voice": "your-voice",
    "response_format": "wav"
  },
  "embedding": { "provider": "your-embedding-provider" },
  "plugin_settings": {
    "your-plugin-guid": {
      "your-plugin-setting": "value"
    }
  }
}
```

Environment overrides:

- `COVAS_SETTINGS_FILE`, default `/app/settings.json`
- `COVAS_PLUGINS_DIR`, default `/app/plugins`
- `COVAS_STT_PROVIDER`, overrides `stt.provider`
- `COVAS_TTS_PROVIDER`, overrides `tts.provider`
- `COVAS_EMBEDDING_PROVIDER`, overrides `embedding.provider`
- `COVAS_TTS_VOICE`, overrides `tts.voice`
- `COVAS_TTS_RESPONSE_FORMAT`, overrides `tts.response_format`
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
  -F model=your-stt-provider \
  -F language=en \
  -F response_format=text \
  -F file=@speech.wav
```

Speech synthesis streams WAV audio:

```bash
curl http://localhost:8000/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"your-tts-provider","voice":"your-voice","input":"Destination reached.","response_format":"wav","speed":1.25}' \
  --output speech.wav
```

Embeddings:

```bash
curl http://localhost:8000/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"your-embedding-provider","input":["Elite Dangerous","COVAS plugin host"]}'
```

## Notes

The host treats TTS output as 24 kHz mono signed 16-bit PCM and prepends a streaming-friendly WAV header for WAV responses.

Transcription supports `json` and `text` response formats. Language and prompt hints are forwarded when the selected STT plugin supports them; Parakeet v3 currently detects its supported languages automatically and does not accept either hint. Speech speed from `0.25` to `4.0` is applied to the PCM stream by the host.

## Test

```bash
uv run python -m unittest discover -s tests
```
