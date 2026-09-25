from __future__ import annotations

import importlib
import json
import os
import queue
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from lib.Logger import log
from lib.Models import EmbeddingModel, STTModel, TTSModel
from lib.PluginBase import PluginBase, PluginManifest
from lib.PluginSettingDefinitions import ModelProviderDefinition


@dataclass
class LoadedPlugin:
    folder: Path
    manifest: PluginManifest
    plugin: PluginBase


@dataclass
class ProviderRecord:
    plugin_guid: str
    plugin_name: str
    provider: ModelProviderDefinition


class ModelPool:
    """A fixed set of independently created model instances leased per request."""

    def __init__(self, models: list[STTModel | TTSModel | EmbeddingModel]):
        if not models:
            raise ValueError("A model pool must contain at least one model")
        self.models = models
        self._available: queue.Queue[STTModel | TTSModel | EmbeddingModel] = queue.Queue(maxsize=len(models))
        for model in models:
            self._available.put_nowait(model)

    @property
    def size(self) -> int:
        return len(self.models)

    def acquire(self, timeout: float | None = None) -> STTModel | TTSModel | EmbeddingModel:
        return self._available.get(timeout=timeout)

    def release(self, model: STTModel | TTSModel | EmbeddingModel) -> None:
        self._available.put(model)

    @contextmanager
    def lease(self) -> Iterator[STTModel | TTSModel | EmbeddingModel]:
        model = self.acquire()
        try:
            yield model
        finally:
            self.release(model)


class PluginHost:
    MAX_MODEL_CONCURRENCY = 64

    def __init__(self, plugins_dir: str | Path, settings: dict[str, Any]):
        self.plugins_dir = Path(plugins_dir)
        self.settings = settings
        self.plugins: list[LoadedPlugin] = []
        self.providers: list[ProviderRecord] = []
        self.failed_plugins: list[dict[str, Any]] = []
        self.model_pools: dict[str, ModelPool | None] = {"stt": None, "tts": None, "embedding": None}
        self.stt_model: STTModel | None = None
        self.tts_model: TTSModel | None = None
        self.embedding_model: EmbeddingModel | None = None

    def load(self) -> "PluginHost":
        plugins_dir = self.plugins_dir.resolve()
        if str(plugins_dir) not in sys.path:
            sys.path.insert(0, str(plugins_dir))

        if not plugins_dir.exists():
            log("warning", f"Plugins directory does not exist: {plugins_dir}")
            return self

        for manifest_path in sorted(plugins_dir.glob("*/manifest.json")):
            self._load_plugin(manifest_path)

        self._register_providers()
        for kind in ("stt", "tts", "embedding"):
            model_pool = self.create_model_pool(
                str(self.settings.get(kind, {}).get("provider", "")),
                kind,
            )
            self.model_pools[kind] = model_pool
            setattr(self, f"{kind}_model", model_pool.models[0] if model_pool else None)
        return self

    def _load_plugin(self, manifest_path: Path) -> None:
        manifest: PluginManifest | None = None
        try:
            plugin_dir = manifest_path.parent.resolve()
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest = PluginManifest(json.load(f))

            deps_dir = plugin_dir / "deps"
            if deps_dir.exists() and str(deps_dir) not in sys.path:
                sys.path.insert(0, str(deps_dir))

            entrypoint = manifest.entrypoint
            if not entrypoint.endswith(".py"):
                raise ValueError(f"Plugin entrypoint is not a Python file: {entrypoint}")

            entrypoint_path = plugin_dir / entrypoint
            if not entrypoint_path.exists():
                raise FileNotFoundError(f"Plugin entrypoint not found: {entrypoint_path}")

            module_name = f"{plugin_dir.name}.{entrypoint[:-3]}"
            module = importlib.import_module(module_name)

            plugin_class: type[PluginBase] | None = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase:
                    plugin_class = attr
                    break

            if plugin_class is None:
                raise TypeError("No PluginBase subclass found")

            plugin = plugin_class(manifest)
            plugin.settings = self.settings.get("plugin_settings", {}).get(manifest.guid, {})
            previous_settings = dict(plugin.settings)
            try:
                settings_version = max(0, int(plugin.settings.get("settings_version", 0)))
            except (TypeError, ValueError):
                settings_version = 0
            target_version = max(0, int(plugin.settings_schema_version))
            while settings_version < target_version:
                plugin.migrate_settings(plugin.settings, settings_version)
                settings_version += 1
                plugin.settings["settings_version"] = settings_version
            if plugin.settings != previous_settings:
                self.settings.setdefault("plugin_settings", {})[manifest.guid] = plugin.settings
            self.plugins.append(LoadedPlugin(folder=plugin_dir, manifest=manifest, plugin=plugin))
            log("info", f"Loaded plugin {manifest.name} ({manifest.guid})")
        except Exception as exc:
            self.failed_plugins.append(
                {
                    "file": os.fspath(manifest_path),
                    "manifest": manifest.__dict__ if manifest else None,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            log("error", f"Failed to load plugin at {manifest_path}: {exc}")

    def _register_providers(self) -> None:
        self.providers = []
        for loaded in self.plugins:
            if not loaded.plugin.model_providers:
                continue
            for provider in loaded.plugin.model_providers:
                self.providers.append(
                    ProviderRecord(
                        plugin_guid=loaded.manifest.guid,
                        plugin_name=loaded.manifest.name,
                        provider=provider,
                    )
                )
                log("info", f"Registered {provider['kind']} provider {provider['id']}")

    def create_model(self, provider_id: str, expected_kind: str) -> STTModel | TTSModel | EmbeddingModel | None:
        if not provider_id:
            return None

        for record in self.providers:
            if record.provider["id"] != provider_id or record.provider["kind"] != expected_kind:
                continue

            plugin = next((loaded.plugin for loaded in self.plugins if loaded.manifest.guid == record.plugin_guid), None)
            if plugin is None:
                continue

            settings = self.settings.get("plugin_settings", {}).get(record.plugin_guid, {})
            model = plugin.create_model(provider_id, settings)
            expected_types = {
                "stt": STTModel,
                "tts": TTSModel,
                "embedding": EmbeddingModel,
            }
            expected_type = expected_types[expected_kind]
            if not isinstance(model, expected_type):
                raise TypeError(f"Provider {provider_id} returned {type(model).__name__}, expected {expected_type.__name__}")
            log("info", f"Created {expected_kind} model {provider_id}")
            return model

        log("warning", f"No {expected_kind} provider found for {provider_id}")
        return None

    def create_model_pool(self, provider_id: str, expected_kind: str) -> ModelPool | None:
        if not provider_id:
            return None

        model_settings = self.settings.get(expected_kind, {})
        concurrency = model_settings.get("concurrency", 1)
        if (
            isinstance(concurrency, bool)
            or not isinstance(concurrency, int)
            or not 1 <= concurrency <= self.MAX_MODEL_CONCURRENCY
        ):
            raise ValueError(
                f"{expected_kind}.concurrency must be an integer between 1 and "
                f"{self.MAX_MODEL_CONCURRENCY}"
            )

        models = [self.create_model(provider_id, expected_kind) for _ in range(concurrency)]
        if any(model is None for model in models):
            return None
        return ModelPool(models)

    def model_list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": record.provider["id"],
                "object": "model",
                "created": 0,
                "owned_by": record.plugin_name,
                "kind": record.provider["kind"],
            }
            for record in self.providers
            if record.provider["kind"] in {"stt", "tts", "embedding"}
        ]
