from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import load_settings


class ConfigTests(unittest.TestCase):
    def test_load_settings_merges_file_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            settings_file.write_text(
                json.dumps(
                    {
                        "tts": {"voice": "selfie"},
                        "plugin_settings": {"plugin-guid": {"value": 1}},
                    }
                ),
                encoding="utf-8",
            )

            env = {
                "COVAS_SETTINGS_FILE": str(settings_file),
                "COVAS_TTS_VOICE": "nova",
                "COVAS_PLUGIN_SETTINGS_JSON": json.dumps({"plugin-guid": {"other": 2}}),
            }
            with patch.dict(os.environ, env, clear=False):
                settings = load_settings()

        self.assertEqual(settings["tts"]["voice"], "nova")
        self.assertEqual(settings["plugin_settings"]["plugin-guid"]["value"], 1)
        self.assertEqual(settings["plugin_settings"]["plugin-guid"]["other"], 2)


if __name__ == "__main__":
    unittest.main()
