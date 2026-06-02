# COVAS Plugin Host

Standalone Docker host for COVAS:NEXT local STT/TTS plugins with an OpenAI-compatible audio API.

The image bakes in:

- Parakeet STT: `COVAS-Labs/plugin-parakeet-stt`
- Pocket TTS: `COVAS-Labs/plugin-pocket-tts`

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
- `COVAS_STT_PROVIDER`, default `parakeet-stt`
- `COVAS_TTS_PROVIDER`, default `pocket-tts`
- `COVAS_TTS_VOICE`, default `nova`
- `COVAS_TTS_RESPONSE_FORMAT`, default `wav`
- `COVAS_PLUGIN_SETTINGS_JSON`, JSON object merged into `plugin_settings`

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
  -d '{"model":"pocket-tts","voice":"nova","input":"Destination reached.","response_format":"wav"}' \
  --output speech.wav
```

## Notes

Pocket TTS produces 24 kHz mono signed 16-bit PCM. The host streams that as WAV by prepending a streaming-friendly WAV header.

## Test

```bash
uv run python -m unittest discover -s tests
```
