from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from lib.Models import EmbeddingModel, STTModel, TTSModel
from app.plugin_loader import PluginHost


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
                    "stt": {"provider": "fake-stt"},
                    "tts": {"provider": "fake-tts"},
                    "embedding": {"provider": "fake-embedding"},
                    "plugin_settings": {},
                },
            ).load()

        self.assertEqual(len(host.failed_plugins), 0)
        self.assertIsInstance(host.stt_model, STTModel)
        self.assertIsInstance(host.tts_model, TTSModel)
        self.assertIsInstance(host.embedding_model, EmbeddingModel)
        self.assertEqual([model["id"] for model in host.model_list()], ["fake-stt", "fake-tts", "fake-embedding"])

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
