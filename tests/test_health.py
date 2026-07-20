from __future__ import annotations

import unittest
from unittest.mock import patch

from app.main import health


class EmptyHost:
    stt_model = None
    tts_model = None
    embedding_model = None
    plugins: list[object] = []
    failed_plugins: list[object] = []

    def model_list(self) -> list[object]:
        return []


class HealthTests(unittest.TestCase):
    def test_empty_host_is_healthy_without_configured_providers(self) -> None:
        with patch("app.main.host", EmptyHost()), patch(
            "app.main.settings",
            {"stt": {}, "tts": {}, "embedding": {}},
        ):
            response = health()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["providers"], [])
        self.assertFalse(response["stt_ready"])
        self.assertFalse(response["tts_ready"])
        self.assertFalse(response["embedding_ready"])


if __name__ == "__main__":
    unittest.main()
