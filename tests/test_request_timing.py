from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from lib.Models import TTSModel


class TimingTTSModel(TTSModel):
    def __init__(self) -> None:
        super().__init__("timing-tts")

    def synthesize(self, text: str, voice: str):
        yield b"abc"
        yield b"de"


class TimingHost:
    stt_model = None
    tts_model = TimingTTSModel()
    embedding_model = None
    plugins: list[object] = []
    failed_plugins: list[object] = []

    def model_list(self) -> list[object]:
        return []


class RequestTimingTests(unittest.TestCase):
    def test_json_response_logs_duration_and_request_id(self) -> None:
        with patch("app.main.host", TimingHost()), patch(
            "app.main.settings",
            {"stt": {}, "tts": {}, "embedding": {}},
        ), self.assertLogs("covas-plugin-host", level="INFO") as logs:
            client = TestClient(app)
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.headers["x-request-id"]), 32)
        self.assertTrue(any("event=request_completed" in message for message in logs.output))
        self.assertTrue(any("duration_ms=" in message for message in logs.output))

    def test_stream_logs_first_byte_and_completion(self) -> None:
        with patch("app.main.host", TimingHost()), patch(
            "app.main.settings",
            {"tts": {"provider": "timing-tts"}},
        ), self.assertLogs("covas-plugin-host", level="INFO") as logs:
            app.state.settings = {}
            client = TestClient(app)
            response = client.post(
                "/v1/audio/speech",
                json={"model": "timing-tts", "voice": "test", "input": "Test", "response_format": "pcm"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"abcde")
        self.assertTrue(any("event=response_started" in message for message in logs.output))
        self.assertTrue(any("event=response_first_byte" in message for message in logs.output))
        self.assertTrue(any("event=request_completed" in message and "bytes_sent=5" in message for message in logs.output))


if __name__ == "__main__":
    unittest.main()
