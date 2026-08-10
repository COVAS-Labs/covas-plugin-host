# COVAS Plugin Host

Standalone Docker host for COVAS:NEXT plugins with an OpenAI-compatible audio API. The image starts only the host service; it does not include, download, install, or configure any plugins.

## Run

Pull the published image:

```bash
docker pull ghcr.io/covas-labs/covas-plugin-host:latest
```

Create the mount sources before starting Docker. If `settings.json` does not
exist, Docker creates a directory at that path and the host cannot start.

```bash
mkdir -p plugins
printf '{}\n' > settings.json
```

Start an empty host:

```bash
docker run --rm --name covas-plugin-host -p 8000:8000 \
  --platform linux/amd64 \
  -v "$PWD/plugins:/app/plugins:ro" \
  -v "$PWD/settings.json:/app/settings.json:ro" \
  ghcr.io/covas-labs/covas-plugin-host:latest
```

In another terminal, verify that the host is running. An empty host reports no
providers by design.

```bash
curl http://localhost:8000/health
curl http://localhost:8000/v1/models
```

The mounted directory must contain one directory per plugin. Extract each
plugin ZIP into its own direct child of `plugins/`; do not place the ZIP itself
there and do not extract its files directly into the `plugins/` root.

```bash
mkdir -p plugins/parakeet-stt
unzip cn-plugin-parakett-stt-*-linux.zip -d plugins/parakeet-stt
```

Each plugin directory must contain `manifest.json`, its Python entrypoint,
models, and a `deps/` directory containing its Python dependencies. The host
does not run plugin installers.

Official `*-linux.zip` plugin release artifacts currently contain Linux x86_64
native dependencies. Use `--platform linux/amd64` as shown above, including on
Apple Silicon and other ARM hosts. The native `linux/arm64` host image can only
load plugins whose dependencies were separately packaged for Linux ARM64.
Windows plugin archives and plugins packaged locally on macOS are not compatible
with the Linux container.

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

## Troubleshooting

Check health before making model requests:

```bash
curl -s http://localhost:8000/health
docker logs covas-plugin-host
```

`/health` reports configured model readiness and includes `failed_plugins` with
the import or initialization error for every plugin that could not load. Common
causes are:

- `settings.json` was not created before `docker run` and was mounted as a directory.
- A plugin ZIP was not extracted into its own direct child of `plugins/`.
- A Windows, macOS, or x86_64 plugin package is being loaded by an incompatible container platform.
- The configured provider does not match the provider ID contributed by the plugin.

Do not send model requests until the corresponding `stt_ready`, `tts_ready`, or
`embedding_ready` value is `true`. An unavailable configured model returns HTTP
503; HTTP 500 indicates an error raised by a model that did load, and its detail
and the container logs should be included in bug reports.

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

The `your-*` values below are placeholders. Install a compatible plugin, select
its actual provider ID in `settings.json`, restart the host, and confirm the
corresponding readiness value in `/health` before using these requests.

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

Transcription supports `json` and `text` response formats. Language and prompt hints are forwarded when the selected STT plugin supports them; Parakeet v3 currently detects its supported languages automatically and does not accept either hint. Speech speed from `0.25` to `4.0` uses in-process WSOLA pitch-preserving time-scale modification while PCM continues to stream.

## Observability

Every response includes an `X-Request-ID` header. The host logs structured timing events to stdout without request bodies, query strings, or authorization data:

- `response_started`: request arrival to handler-ready time.
- `response_first_byte`: server-side time to the first response-body byte.
- `request_completed`: total duration, first-byte time, bytes sent, and whether the stream completed or was interrupted.
- `request_failed`: unhandled endpoint failures with elapsed time.

## Test

```bash
uv run python -m unittest discover -s tests
```
