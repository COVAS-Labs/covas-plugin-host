from __future__ import annotations

import os
import struct
import subprocess
import tempfile
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Iterable

import speech_recognition as sr


TTS_SAMPLE_RATE = 24000
TTS_CHANNELS = 1
TTS_SAMPLE_WIDTH = 2


def decode_upload_to_audio_data(data: bytes, filename: str | None = None) -> sr.AudioData:
    suffix = Path(filename or "audio").suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix) as source, tempfile.NamedTemporaryFile(suffix=".wav") as converted:
        source.write(data)
        source.flush()

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            source.name,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            converted.name,
        ]
        result = subprocess.run(command, capture_output=True, check=False)
        if result.returncode != 0:
            error = result.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(f"Failed to decode audio with ffmpeg: {error}")

        with sr.AudioFile(converted.name) as audio_source:
            recognizer = sr.Recognizer()
            return recognizer.record(audio_source)


def wav_stream_header(
    sample_rate: int = TTS_SAMPLE_RATE,
    channels: int = TTS_CHANNELS,
    sample_width: int = TTS_SAMPLE_WIDTH,
    data_size: int = 0x7FFF_F000,
) -> bytes:
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        min(36 + data_size, 0xFFFF_FFFF),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
        b"data",
        data_size,
    )


def wav_chunks(pcm_chunks: Iterable[bytes]) -> Iterable[bytes]:
    yield wav_stream_header()
    yield from pcm_chunks


def adjust_pcm_speed(pcm_chunks: Iterable[bytes], speed: float) -> Iterable[bytes]:
    if speed == 1:
        yield from pcm_chunks
        return

    remaining_speed = speed
    filters = []
    while remaining_speed > 2:
        filters.append("atempo=2")
        remaining_speed /= 2
    while remaining_speed < 0.5:
        filters.append("atempo=0.5")
        remaining_speed /= 0.5
    if remaining_speed != 1:
        filters.append(f"atempo={remaining_speed:g}")

    process = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            str(TTS_SAMPLE_RATE),
            "-ac",
            str(TTS_CHANNELS),
            "-i",
            "pipe:0",
            "-af",
            ",".join(filters),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "pipe:1",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    output: Queue[bytes | None] = Queue()
    stderr: list[bytes] = []

    def read_stdout() -> None:
        try:
            while chunk := os.read(process.stdout.fileno(), 8192):
                output.put(chunk)
        finally:
            output.put(None)

    def read_stderr() -> None:
        stderr.append(process.stderr.read())

    stdout_thread = Thread(target=read_stdout, daemon=True)
    stderr_thread = Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    try:
        for chunk in pcm_chunks:
            process.stdin.write(chunk)
            process.stdin.flush()
            while True:
                try:
                    adjusted = output.get_nowait()
                except Empty:
                    break
                if adjusted is not None:
                    yield adjusted

        process.stdin.close()
        while adjusted := output.get():
            yield adjusted

        returncode = process.wait()
        stderr_thread.join()
        if returncode != 0:
            error = b"".join(stderr).decode("utf-8", errors="replace").strip()
            raise ValueError(f"Failed to adjust speech speed with ffmpeg: {error}")
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        if process.poll() is None:
            process.terminate()
            process.wait()
        stdout_thread.join()
        stderr_thread.join()
        process.stdout.close()
        process.stderr.close()
