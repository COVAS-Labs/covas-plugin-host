# Plugin Host Load Test

This closed-loop load test keeps one persistent HTTP connection per worker. Each worker sends its next request immediately after the previous response body finishes. Every endpoint runs at 1, 2, 3, and 4 concurrent connections by default.

The report includes successful throughput, HTTP status counts, and E2E latency percentiles. TTS requests raw PCM so its time to first response-body byte (TTFB) measures the first generated audio rather than an immediately emitted WAV container header. TTS also reports per-stream RTF (`request E2E time / audio duration`), aggregate RTF (`total audio duration / stage wall time`), and estimated chunk-arrival underflows assuming playback begins on receipt of the first audio chunk with no additional startup buffer. RTF ≤ 1 means the complete response took no longer than its audio duration, but only the chunk-arrival check detects pauses within that response. Failed responses are excluded from latency and successful-throughput calculations but remain visible in status counts and attempted throughput in the JSON report.

## Run

Use the project environment, and provide the key through the environment so it is not stored in shell history or the repository:

```bash
read -s COVAS_API_KEY
export COVAS_API_KEY
uv run python load-test/load_test.py \
  --duration 10 \
  --output load-test/results/run.json
unset COVAS_API_KEY
```

`COVAS_API_KEY` is optional for local deployments that have authentication disabled.

Run one endpoint or cap requests per connection for a smoke test:

```bash
uv run python load-test/load_test.py --endpoint tts --duration 5
uv run python load-test/load_test.py --requests-per-connection 2 --duration 30
```

By default STT uses a generated three-second tone, which exercises inference but is not representative speech. Supply a fixed spoken fixture for meaningful production numbers:

```bash
uv run python load-test/load_test.py --stt-audio /path/to/speech.wav
```

Useful options:

- `--connections 1 2 3 4` selects the stages.
- `--pause 2` inserts a pause between stages.
- `--include-raw` includes every request sample in the JSON report.
- `--tts-voice NAME` overrides the deployed default voice.
- `--base-url URL` targets another deployment.

Do not commit API keys or reports containing operational data.
