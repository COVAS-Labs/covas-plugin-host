from __future__ import annotations

import struct
import subprocess
import tempfile
from pathlib import Path
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
