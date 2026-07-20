from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from lib.Models import STTModel, TTSModel


class FakeSTTModel(STTModel):
    def __init__(self):
        super().__init__("fake-stt")
        self.options: dict[str, str | None] | None = None

    def transcribe(self, audio, *, language=None, prompt=None):
        self.options = {"language": language, "prompt": prompt}
        return "transcribed text"


class BasicSTTModel(STTModel):
    def __init__(self):
        super().__init__("basic-stt")

    def transcribe(self, audio):
        return "transcribed text"


class FakeTTSModel(TTSModel):
    def __init__(self):
        super().__init__("fake-tts")

    def synthesize(self, text, voice):
        yield b"\x00\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05\x00\x06\x00\x07\x00"


class FakeHost:
    def __init__(self, stt_model: STTModel, tts_model: TTSModel):
        self.stt_model = stt_model
        self.tts_model = tts_model
        self.embedding_model = None


class AudioEndpointTests(unittest.TestCase):
    def test_transcription_forwards_supported_hints_and_returns_text(self) -> None:
        stt_model = FakeSTTModel()
        host = FakeHost(stt_model, FakeTTSModel())
        with (
            patch("app.main.host", host),
            patch("app.main.settings", {"stt": {"provider": "fake-stt"}}),
            patch("app.main.decode_upload_to_audio_data", return_value=object()),
        ):
            app.state.settings = {}
            client = TestClient(app)
            response = client.post(
                "/v1/audio/transcriptions",
                data={"model": "fake-stt", "language": "de", "prompt": "Commander", "response_format": "text"},
                files={"file": ("speech.wav", b"audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(response.text, "transcribed text")
        self.assertEqual(stt_model.options, {"language": "de", "prompt": "Commander"})

    def test_transcription_rejects_hints_unsupported_by_plugin(self) -> None:
        host = FakeHost(BasicSTTModel(), FakeTTSModel())
        with (
            patch("app.main.host", host),
            patch("app.main.settings", {"stt": {"provider": "basic-stt"}}),
            patch("app.main.decode_upload_to_audio_data", return_value=object()),
        ):
            app.state.settings = {}
            client = TestClient(app)
            response = client.post(
                "/v1/audio/transcriptions",
                data={"model": "basic-stt", "language": "de"},
                files={"file": ("speech.wav", b"audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "STT model does not support: language")

    def test_speech_applies_requested_speed(self) -> None:
        host = FakeHost(FakeSTTModel(), FakeTTSModel())
        with patch("app.main.host", host), patch("app.main.settings", {"tts": {"provider": "fake-tts"}}):
            app.state.settings = {}
            client = TestClient(app)
            response = client.post(
                "/v1/audio/speech",
                json={"model": "fake-tts", "input": "Test", "response_format": "pcm", "speed": 2},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/pcm")
        self.assertLess(len(response.content), 16)


if __name__ == "__main__":
    unittest.main()
