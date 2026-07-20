from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

import speech_recognition as sr


class LLMError(Exception):
    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class LLMModel(ABC):
    model_name: str
    provider_name: str | None

    def __init__(self, model_name: str, provider_name: str | None = None):
        self.model_name = model_name
        self.provider_name = provider_name


class EmbeddingModel(ABC):
    model_name: str

    def __init__(self, model_name: str):
        self.model_name = model_name

    @abstractmethod
    def create_embedding(self, input_text: str) -> tuple[str, list[float]]:
        pass



class STTModel(ABC):
    model_name: str
    provider_name: str | None

    def __init__(self, model_name: str, provider_name: str | None = None):
        self.model_name = model_name
        self.provider_name = provider_name

    @abstractmethod
    def transcribe(
        self,
        audio: sr.AudioData,
        *,
        language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        pass


class TTSModel(ABC):
    model_name: str
    provider_name: str | None

    def __init__(self, model_name: str, provider_name: str | None = None):
        self.model_name = model_name
        self.provider_name = provider_name

    @abstractmethod
    def synthesize(self, text: str, voice: str) -> Iterable[bytes]:
        pass
