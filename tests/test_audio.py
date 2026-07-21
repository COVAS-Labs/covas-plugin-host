from __future__ import annotations

import io
import unittest
import wave

import numpy as np

from app.audio import TTS_SAMPLE_RATE, adjust_pcm_speed, decode_upload_to_audio_data


class AudioTests(unittest.TestCase):
    def test_decode_upload_converts_to_16khz_mono_pcm(self) -> None:
        source = io.BytesIO()
        with wave.open(source, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(TTS_SAMPLE_RATE)
            wav.writeframes(b"\x00\x00" * TTS_SAMPLE_RATE)

        audio = decode_upload_to_audio_data(source.getvalue(), "speech.wav")

        self.assertEqual(audio.sample_rate, 16000)
        self.assertEqual(audio.sample_width, 2)
        self.assertEqual(len(audio.frame_data), 32000)

    def test_adjust_pcm_speed_streams_after_first_chunk(self) -> None:
        samples = (np.sin(np.linspace(0, 100, TTS_SAMPLE_RATE)) * 16000).astype(np.int16)
        pcm = samples.tobytes()
        chunks = [pcm[offset:offset + 4800] for offset in range(0, len(pcm), 4800)]

        class ChunkSource:
            consumed = 0

            def __iter__(self):
                for chunk in chunks:
                    self.consumed += 1
                    yield chunk

        source = ChunkSource()
        stream = adjust_pcm_speed(source, 1.2)
        first = next(stream)
        self.assertLess(source.consumed, len(chunks))
        faster = first + b"".join(stream)

        self.assertGreater(len(faster), 0)
        self.assertLess(len(faster), len(pcm))


if __name__ == "__main__":
    unittest.main()
