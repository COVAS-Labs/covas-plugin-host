from __future__ import annotations

import struct
from typing import Iterable

import miniaudio
import numpy as np
import speech_recognition as sr
from audiotsm import wsola
from audiotsm.io.array import ArrayReader, ArrayWriter


TTS_SAMPLE_RATE = 24000
TTS_CHANNELS = 1
TTS_SAMPLE_WIDTH = 2


def decode_upload_to_audio_data(data: bytes, filename: str | None = None) -> sr.AudioData:
    try:
        decoded = miniaudio.decode(
            data,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=16000,
        )
    except miniaudio.DecodeError as exc:
        label = filename or "upload"
        raise ValueError(f"Failed to decode audio upload {label}: {exc}") from exc
    return sr.AudioData(decoded.samples.tobytes(), sample_rate=16000, sample_width=2)


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

    tsm = wsola(TTS_CHANNELS, speed=speed)

    def write_output(writer: ArrayWriter) -> bytes:
        output = writer.data
        if output.size == 0:
            return b""
        clipped = np.clip(output[0], -1.0, 1.0)
        return (clipped * 32767.0).astype(np.int16).tobytes()

    for chunk in pcm_chunks:
        if not chunk:
            continue
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        writer = ArrayWriter(TTS_CHANNELS)
        tsm.run(ArrayReader(samples.reshape(TTS_CHANNELS, -1)), writer, flush=False)
        if adjusted := write_output(writer):
            yield adjusted

    finished = False
    while not finished:
        writer = ArrayWriter(TTS_CHANNELS)
        _, finished = tsm.flush_to(writer)
        if adjusted := write_output(writer):
            yield adjusted
