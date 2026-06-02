from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "plugins_dir": "/app/plugins",
    "stt": {
        "provider": "parakeet-stt",
    },
    "tts": {
        "provider": "pocket-tts",
        "voice": "nova",
        "response_format": "wav",
    },
    "plugin_settings": {
        "b7ddc677-0cfc-4081-af61-b2ebc2af5fe3": {
            "num_steps": 2,
            "max_tokens": 50,
            "inter_pass_gap_ms": 150,
        }
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Settings file must contain a JSON object: {path}")
    return data


def load_settings() -> dict[str, Any]:
    settings = deepcopy(DEFAULT_SETTINGS)

    env_settings_file = os.getenv("COVAS_SETTINGS_FILE")
    settings_file = Path(env_settings_file or "/app/settings.json")
    settings = _deep_merge(settings, _load_json_file(settings_file))

    if os.getenv("COVAS_PLUGINS_DIR"):
        settings["plugins_dir"] = os.environ["COVAS_PLUGINS_DIR"]
    if os.getenv("COVAS_STT_PROVIDER"):
        settings.setdefault("stt", {})["provider"] = os.environ["COVAS_STT_PROVIDER"]
    if os.getenv("COVAS_TTS_PROVIDER"):
        settings.setdefault("tts", {})["provider"] = os.environ["COVAS_TTS_PROVIDER"]
    if os.getenv("COVAS_TTS_VOICE"):
        settings.setdefault("tts", {})["voice"] = os.environ["COVAS_TTS_VOICE"]
    if os.getenv("COVAS_TTS_RESPONSE_FORMAT"):
        settings.setdefault("tts", {})["response_format"] = os.environ["COVAS_TTS_RESPONSE_FORMAT"]

    plugin_settings_json = os.getenv("COVAS_PLUGIN_SETTINGS_JSON")
    if plugin_settings_json:
        parsed = json.loads(plugin_settings_json)
        if not isinstance(parsed, dict):
            raise ValueError("COVAS_PLUGIN_SETTINGS_JSON must be a JSON object")
        settings["plugin_settings"] = _deep_merge(settings.get("plugin_settings", {}), parsed)

    return settings
