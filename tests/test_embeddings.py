from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from lib.Models import EmbeddingModel
from app.main import app


class FakeEmbeddingModel(EmbeddingModel):
    def __init__(self):
        super().__init__("fake-embedding")

    def create_embedding(self, input_text: str) -> tuple[str, list[float]]:
        return self.model_name, [float(len(input_text)), float("nan")]


class FakeHost:
    stt_model = None
    tts_model = None
    embedding_model = FakeEmbeddingModel()


class EmbeddingsEndpointTests(unittest.TestCase):
    def test_embeddings_response_shape(self) -> None:
        with patch("app.main.host", FakeHost()), patch("app.main.settings", {"embedding": {"provider": "fake-embedding"}}):
            app.state.settings = {}
            client = TestClient(app)
            response = client.post(
                "/v1/embeddings",
                json={"model": "fake-embedding", "input": ["one", "three"]},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "list")
        self.assertEqual(payload["model"], "fake-embedding")
        self.assertEqual(payload["data"][0]["embedding"], [3.0, 0.0])
        self.assertEqual(payload["data"][1]["embedding"], [5.0, 0.0])


if __name__ == "__main__":
    unittest.main()
