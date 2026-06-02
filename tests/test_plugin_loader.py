from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from lib.Models import STTModel, TTSModel
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
                    from lib.PluginHelper import STTModel, TTSModel

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

                    class FakePlugin(PluginBase):
                        def __init__(self, plugin_manifest):
                            super().__init__(plugin_manifest)
                            self.model_providers = [
                                {'kind': 'stt', 'id': 'fake-stt', 'label': 'Fake STT', 'settings_config': []},
                                {'kind': 'tts', 'id': 'fake-tts', 'label': 'Fake TTS', 'settings_config': []},
                            ]
                        def create_model(self, provider_id, settings):
                            if provider_id == 'fake-stt':
                                return FakeSTT()
                            if provider_id == 'fake-tts':
                                return FakeTTS()
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
                    "plugin_settings": {},
                },
            ).load()

        self.assertEqual(len(host.failed_plugins), 0)
        self.assertIsInstance(host.stt_model, STTModel)
        self.assertIsInstance(host.tts_model, TTSModel)
        self.assertEqual([model["id"] for model in host.model_list()], ["fake-stt", "fake-tts"])


if __name__ == "__main__":
    unittest.main()
