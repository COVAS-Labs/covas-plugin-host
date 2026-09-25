from __future__ import annotations

import json
import tempfile
import textwrap
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib.Models import EmbeddingModel, STTModel, TTSModel
from app.plugin_loader import ModelPool, PluginHost


class PluginLoaderTests(unittest.TestCase):
    def test_loads_plugin_and_creates_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "fake_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
            (plugin_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "guid": "fake-guid",
                        "name": "Fake Plugin",
                        "version": "1.0.0",
                        "entrypoint": "fake_plugin.py",
                    }
                ),
                encoding="utf-8",
            )
            (plugin_dir / "fake_plugin.py").write_text(
                textwrap.dedent(
                    """
                    from lib.PluginBase import PluginBase
                    from lib.PluginHelper import EmbeddingModel, STTModel, TTSModel

                    class FakeSTT(STTModel):
                        def __init__(self):
                            super().__init__('fake-stt')
                        def transcribe(self, audio):
                            return 'ok'

                    class FakeTTS(TTSModel):
                        def __init__(self):
                            super().__init__('fake-tts')
                        def synthesize(self, text, voice):
                            yield b'audio'

                    class FakeEmbedding(EmbeddingModel):
                        def __init__(self):
                            super().__init__('fake-embedding')
                        def create_embedding(self, input_text):
                            return ('fake-embedding', [1.0, 2.0, 3.0])

                    class FakePlugin(PluginBase):
                        def __init__(self, plugin_manifest):
                            super().__init__(plugin_manifest)
                            self.model_providers = [
                                {'kind': 'stt', 'id': 'fake-stt', 'label': 'Fake STT', 'settings_config': []},
                                {'kind': 'tts', 'id': 'fake-tts', 'label': 'Fake TTS', 'settings_config': []},
                                {'kind': 'embedding', 'id': 'fake-embedding', 'label': 'Fake Embedding', 'settings_config': []},
                            ]
                        def create_model(self, provider_id, settings):
                            if provider_id == 'fake-stt':
                                return FakeSTT()
                            if provider_id == 'fake-tts':
                                return FakeTTS()
                            if provider_id == 'fake-embedding':
                                return FakeEmbedding()
                            raise ValueError(provider_id)
                    """
                ),
                encoding="utf-8",
            )

            host = PluginHost(
                tmp,
                {
                    "stt": {"provider": "fake-stt", "concurrency": 2},
                    "tts": {"provider": "fake-tts", "concurrency": 3},
                    "embedding": {"provider": "fake-embedding"},
                    "plugin_settings": {},
                },
            ).load()

        self.assertEqual(len(host.failed_plugins), 0)
        self.assertIsInstance(host.stt_model, STTModel)
        self.assertIsInstance(host.tts_model, TTSModel)
        self.assertIsInstance(host.embedding_model, EmbeddingModel)
        self.assertEqual([model["id"] for model in host.model_list()], ["fake-stt", "fake-tts", "fake-embedding"])
        self.assertEqual(
            {kind: pool.size for kind, pool in host.model_pools.items() if pool is not None},
            {"stt": 2, "tts": 3, "embedding": 1},
        )
        self.assertEqual(len({id(model) for model in host.model_pools["tts"].models}), 3)

    def test_model_concurrency_must_be_a_supported_integer(self) -> None:
        for concurrency in (0, 65, 1.5, True):
            with self.subTest(concurrency=concurrency):
                host = PluginHost("/plugins", {"tts": {"concurrency": concurrency}})
                with self.assertRaisesRegex(ValueError, "tts.concurrency"):
                    host.create_model_pool("pocket-tts", "tts")

    def test_model_pool_queues_until_an_instance_is_released(self) -> None:
        first, second = object(), object()
        pool = ModelPool([first, second])
        waiting = threading.Event()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with pool.lease() as leased_first:
                with pool.lease() as leased_second:
                    future = executor.submit(lambda: (waiting.set(), pool.acquire())[1])
                    self.assertTrue(waiting.wait(timeout=1))
                    self.assertFalse(future.done())

                acquired = future.result(timeout=1)
                self.assertIs(acquired, leased_second)
                pool.release(acquired)

        returned = {id(pool.acquire()), id(pool.acquire())}
        self.assertEqual(returned, {id(first), id(second)})

    def test_migrates_plugin_settings_to_declared_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "migrating_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
            (plugin_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "guid": "migrating-guid",
                        "name": "Migrating Plugin",
                        "version": "1.0.0",
                        "entrypoint": "migrating_plugin.py",
                    }
                ),
                encoding="utf-8",
            )
            (plugin_dir / "migrating_plugin.py").write_text(
                textwrap.dedent(
                    """
                    from lib.PluginBase import PluginBase

                    class MigratingPlugin(PluginBase):
                        settings_schema_version = 2

                        def __init__(self, plugin_manifest):
                            super().__init__(plugin_manifest)

                        def migrate_settings(self, settings, from_version):
                            if from_version == 0:
                                settings['threads'] = min(4, settings.get('threads', 4))
                            elif from_version == 1:
                                settings['second_step_applied'] = True
                    """
                ),
                encoding="utf-8",
            )
            settings = {
                "stt": {"provider": ""},
                "tts": {"provider": ""},
                "embedding": {"provider": ""},
                "plugin_settings": {"migrating-guid": {"threads": 8}},
            }

            host = PluginHost(tmp, settings).load()

        self.assertEqual(len(host.failed_plugins), 0)
        self.assertEqual(
            settings["plugin_settings"]["migrating-guid"],
            {"threads": 4, "second_step_applied": True, "settings_version": 2},
        )


if __name__ == "__main__":
    unittest.main()
