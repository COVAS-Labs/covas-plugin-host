from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, cast

from .PluginSettingDefinitions import ModelProviderDefinition, PluginSettings


class PluginManifest:
    guid: str = ""
    name: str = ""
    author: str = ""
    version: str = ""
    repository: str = ""
    description: str = ""
    entrypoint: str = ""

    def __init__(self, j: str | dict[str, Any]) -> None:
        data = j if isinstance(j, dict) else json.loads(j)
        self.__dict__.update(cast(dict[str, str], data))


class PluginBase(ABC):
    plugin_manifest: PluginManifest
    settings_config: PluginSettings | None = None
    settings: dict[str, Any] = {}
    model_providers: list[ModelProviderDefinition] | None = None

    @abstractmethod
    def __init__(self, plugin_manifest: PluginManifest):
        self.plugin_manifest = plugin_manifest

    def on_chat_start(self, helper: Any):
        pass

    def on_chat_stop(self, helper: Any):
        pass

    def create_model(self, provider_id: str, settings: dict[str, Any]):
        raise NotImplementedError(
            f"Plugin {self.plugin_manifest.name} defines model_providers but does not implement create_model()"
        )
