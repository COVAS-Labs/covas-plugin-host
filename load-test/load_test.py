#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
import wave
from collections import Counter
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://ai.covaslabs.com"
ENDPOINTS = ("tts", "stt", "embedding")


@dataclass
class RequestResult:
    status: int | None
    e2e_ms: float
    ttfb_ms: float | None
    bytes_received: int
    error: str | None = None
    audio_seconds: float | None = None
    stream_rtf: float | None = None
    audio_underrun_events: int = 0
    minimum_buffer_seconds: float | None = None


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values: list[float]) -> dict[str, float | None]:
    return {
        "min": min(values) if values else None,
        "mean": statistics.fmean(values) if values else None,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values) if values else None,
    }


def synthetic_wav(duration_seconds: float = 3.0, sample_rate: int = 16_000) -> bytes:
    """Create a deterministic fallback input that still exercises STT inference."""
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for index in range(int(duration_seconds * sample_rate)):
            sample = int(5_000 * math.sin(2 * math.pi * 220 * index / sample_rate))
            frames.extend(sample.to_bytes(2, "little", signed=True))
        wav_file.writeframes(frames)
    return output.getvalue()


def build_request(
    client: httpx.AsyncClient,
    endpoint: str,
    args: argparse.Namespace,
    stt_audio: bytes,
) -> httpx.Request:
    if endpoint == "tts":
        payload: dict[str, Any] = {
            "model": args.tts_model,
            "input": args.tts_text,
            "response_format": "pcm",
        }
        if args.tts_voice:
            payload["voice"] = args.tts_voice
        return client.build_request("POST", "/v1/audio/speech", json=payload)

    if endpoint == "stt":
        return client.build_request(
            "POST",
            "/v1/audio/transcriptions",
            data={"model": args.stt_model, "response_format": "json"},
            files={"file": ("load-test.wav", stt_audio, "audio/wav")},
        )

    return client.build_request(
        "POST",
        "/v1/embeddings",
        json={"model": args.embedding_model, "input": args.embedding_text},
    )


async def execute_request(
    client: httpx.AsyncClient,
    endpoint: str,
    args: argparse.Namespace,
    stt_audio: bytes,
) -> RequestResult:
    started_at = time.perf_counter()
    first_byte_at: float | None = None
    status: int | None = None
    bytes_received = 0
    audio_underrun_events = 0
    minimum_buffer_seconds: float | None = None
    try:
        request = build_request(client, endpoint, args, stt_audio)
        response = await client.send(request, stream=True)
        status = response.status_code
        async for chunk in response.aiter_raw():
            if chunk and first_byte_at is None:
                first_byte_at = time.perf_counter()
            bytes_received += len(chunk)
            if endpoint == "tts" and chunk and first_byte_at is not None:
                produced_audio_seconds = bytes_received / (24_000 * 1 * 2)
                elapsed_since_first_byte = time.perf_counter() - first_byte_at
                buffered_seconds = produced_audio_seconds - elapsed_since_first_byte
                minimum_buffer_seconds = (
                    buffered_seconds
                    if minimum_buffer_seconds is None
                    else min(minimum_buffer_seconds, buffered_seconds)
                )
                if buffered_seconds < 0:
                    audio_underrun_events += 1
        await response.aclose()
        finished_at = time.perf_counter()
        audio_seconds = bytes_received / (24_000 * 1 * 2) if endpoint == "tts" and status and 200 <= status < 300 else None
        return RequestResult(
            status=status,
            e2e_ms=(finished_at - started_at) * 1_000,
            ttfb_ms=(first_byte_at - started_at) * 1_000 if endpoint == "tts" and first_byte_at else None,
            bytes_received=bytes_received,
            audio_seconds=audio_seconds,
            stream_rtf=((finished_at - started_at) / audio_seconds) if audio_seconds else None,
            audio_underrun_events=audio_underrun_events,
            minimum_buffer_seconds=minimum_buffer_seconds,
        )
    except Exception as exc:
        return RequestResult(
            status=status,
            e2e_ms=(time.perf_counter() - started_at) * 1_000,
            ttfb_ms=None,
            bytes_received=bytes_received,
            error=f"{type(exc).__name__}: {exc}",
        )


async def worker(
    endpoint: str,
    args: argparse.Namespace,
    stt_audio: bytes,
    start_event: asyncio.Event,
) -> list[RequestResult]:
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
    timeout = httpx.Timeout(args.timeout)
    results: list[RequestResult] = []
    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}
    async with httpx.AsyncClient(
        base_url=args.base_url,
        headers=headers,
        limits=limits,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        await start_event.wait()
        deadline = time.perf_counter() + args.duration
        while time.perf_counter() < deadline:
            if args.requests_per_connection and len(results) >= args.requests_per_connection:
                break
            results.append(await execute_request(client, endpoint, args, stt_audio))
    return results


async def run_stage(
    endpoint: str,
    connections: int,
    args: argparse.Namespace,
    stt_audio: bytes,
) -> dict[str, Any]:
    start_event = asyncio.Event()
    tasks = [
        asyncio.create_task(worker(endpoint, args, stt_audio, start_event))
        for _ in range(connections)
    ]
    await asyncio.sleep(0)
    stage_started = time.perf_counter()
    start_event.set()
    nested_results = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - stage_started
    results = [result for worker_results in nested_results for result in worker_results]
    successful = [result for result in results if result.status is not None and 200 <= result.status < 300]
    statuses = Counter(str(result.status) if result.status is not None else "error" for result in results)
    errors = Counter(result.error for result in results if result.error)
    return {
        "endpoint": endpoint,
        "connections": connections,
        "elapsed_seconds": elapsed,
        "requests": len(results),
        "successful_requests": len(successful),
        "throughput_rps": len(successful) / elapsed if elapsed else 0,
        "attempted_rps": len(results) / elapsed if elapsed else 0,
        "status_counts": dict(statuses),
        "errors": dict(errors),
        "e2e_ms": distribution([result.e2e_ms for result in successful]),
        "ttfb_ms": distribution([result.ttfb_ms for result in successful if result.ttfb_ms is not None]),
        "bytes_received": sum(result.bytes_received for result in successful),
        "audio_seconds_generated": sum(result.audio_seconds or 0 for result in successful),
        "aggregate_rtf": (
            sum(result.audio_seconds or 0 for result in successful) / elapsed
            if endpoint == "tts" and elapsed
            else None
        ),
        "stream_rtf": distribution(
            [result.stream_rtf for result in successful if result.stream_rtf is not None]
        ),
        "streams_with_audio_underruns": sum(
            result.audio_underrun_events > 0 for result in successful
        ),
        "audio_underrun_events": sum(result.audio_underrun_events for result in successful),
        "minimum_buffer_seconds": distribution(
            [
                result.minimum_buffer_seconds
                for result in successful
                if result.minimum_buffer_seconds is not None
            ]
        ),
        "raw_results": [asdict(result) for result in results] if args.include_raw else None,
    }


def format_number(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def print_stage(stage: dict[str, Any]) -> None:
    latency = stage["e2e_ms"]
    ttfb = stage["ttfb_ms"]
    stream_rtf = stage["stream_rtf"]
    print(
        f"{stage['endpoint']:<9} {stage['connections']:>4} "
        f"{stage['successful_requests']:>5}/{stage['requests']:<5} "
        f"{stage['throughput_rps']:>8.2f} "
        f"{format_number(latency['p50']):>9} {format_number(latency['p95']):>9} "
        f"{format_number(latency['p99']):>9} {format_number(ttfb['p50']):>10} "
        f"{format_number(ttfb['p95']):>10} "
        f"{format_number(stage['aggregate_rtf']):>8} "
        f"{format_number(stream_rtf['p50']):>8} {format_number(stream_rtf['p95']):>8} "
        f"{format_number(stream_rtf['max']):>8} "
        f"{stage['streams_with_audio_underruns']:>5} "
        f"{json.dumps(stage['status_counts'], sort_keys=True)}"
    )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.stt_audio:
        stt_audio = Path(args.stt_audio).read_bytes()
    else:
        stt_audio = synthetic_wav()
        print("No --stt-audio supplied; using a 3-second synthetic WAV.", file=sys.stderr)

    selected = list(ENDPOINTS) if args.endpoint == "all" else [args.endpoint]
    report: dict[str, Any] = {
        "base_url": args.base_url,
        "duration_seconds": args.duration,
        "requests_per_connection": args.requests_per_connection,
        "stages": [],
    }
    print("endpoint  conn    ok/total      req/s   e2e p50   e2e p95   e2e p99   ttfb p50   ttfb p95  agg RTF stream50 stream95 streamMax underruns statuses")
    for endpoint in selected:
        for connections in args.connections:
            stage = await run_stage(endpoint, connections, args, stt_audio)
            report["stages"].append(stage)
            print_stage(stage)
            if args.pause:
                await asyncio.sleep(args.pause)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Closed-loop load test for the COVAS plugin host")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default=os.getenv("COVAS_API_KEY"), help=argparse.SUPPRESS)
    parser.add_argument("--endpoint", choices=("all", *ENDPOINTS), default="all")
    parser.add_argument("--connections", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--duration", type=float, default=10, help="Maximum seconds per stage")
    parser.add_argument(
        "--requests-per-connection",
        type=int,
        default=0,
        help="Optional per-stage request cap for each connection (0 is unlimited)",
    )
    parser.add_argument("--pause", type=float, default=0, help="Seconds to pause between stages")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--stt-audio", help="Path to a realistic WAV/MP3/FLAC fixture")
    parser.add_argument("--stt-model", default="parakeet-stt")
    parser.add_argument("--tts-model", default="pocket-tts")
    parser.add_argument("--tts-voice", help="Omit to use the server-configured voice")
    parser.add_argument("--embedding-model", default="granite-embedding")
    parser.add_argument("--tts-text", default="Commander, your destination is twelve light seconds away.")
    parser.add_argument("--embedding-text", default="Flight control telemetry for the COVAS plugin host.")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    parser.add_argument("--include-raw", action="store_true", help="Include every request sample in JSON output")
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be positive")
    if any(connection <= 0 for connection in args.connections):
        parser.error("--connections values must be positive")
    if args.requests_per_connection < 0:
        parser.error("--requests-per-connection cannot be negative")
    return args


def main() -> None:
    args = parse_args()
    report = asyncio.run(run(args))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
