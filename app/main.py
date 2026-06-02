from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Literal

import contextlib
from collections.abc import Iterable, Iterator

import anyio
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .auth import verify_request
from .audio import decode_upload_to_audio_data
from .config import load_settings
from .plugin_loader import PluginHost


class SpeechRequest(BaseModel):
    model: str | None = None
    input: str = Field(min_length=1)
    voice: str | None = None
    response_format: Literal["wav", "pcm"] | None = None
    speed: float | None = None


settings: dict[str, Any] = {}
host: PluginHost | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global settings, host
    settings = load_settings()
    app.state.settings = settings
    host = PluginHost(settings["plugins_dir"], settings).load()
    yield


app = FastAPI(title="COVAS Plugin Host", version="0.1.0", lifespan=lifespan)


def _next_chunk(iterator: Iterator[bytes]) -> tuple[bool, bytes]:
    try:
        return True, next(iterator)
    except StopIteration:
        return False, b""


async def _stream_audio(request: Request, chunks: Iterable[bytes], include_wav_header: bool) -> Any:
    iterator = iter(chunks)
    close = getattr(iterator, "close", None)
    try:
        if include_wav_header:
            from .audio import wav_stream_header

            yield wav_stream_header()

        while True:
            if await request.is_disconnected():
                break

            has_chunk, chunk = await anyio.to_thread.run_sync(_next_chunk, iterator)
            if not has_chunk:
                break
            if chunk:
                yield chunk
    finally:
        if close is not None:
            with contextlib.suppress(Exception):
                close()


def _host() -> PluginHost:
    if host is None:
        raise HTTPException(status_code=503, detail="Plugin host is not initialized")
    return host


@app.get("/health")
def health() -> dict[str, Any]:
    current = _host()
    return {
        "status": "ok" if current.stt_model is not None and current.tts_model is not None else "degraded",
        "plugins": [loaded.manifest.__dict__ for loaded in current.plugins],
        "providers": current.model_list(),
        "failed_plugins": current.failed_plugins,
        "stt_ready": current.stt_model is not None,
        "tts_ready": current.tts_model is not None,
    }


@app.get("/v1/models")
def list_models(auth: Any = Depends(verify_request)) -> dict[str, Any]:
    return {"object": "list", "data": _host().model_list()}


@app.post("/v1/audio/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
    language: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
    response_format: str | None = Form(default="json"),
    auth: Any = Depends(verify_request),
) -> JSONResponse:
    current = _host()
    if current.stt_model is None:
        raise HTTPException(status_code=503, detail="STT model is not available")

    requested_model = model or settings.get("stt", {}).get("provider")
    if requested_model and requested_model != settings.get("stt", {}).get("provider"):
        raise HTTPException(status_code=404, detail=f"STT model not loaded: {requested_model}")

    data = await file.read()
    try:
        audio = decode_upload_to_audio_data(data, file.filename)
        text = current.stt_model.transcribe(audio)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse({"text": text})


@app.post("/v1/audio/speech")
def create_speech(
    request: Request,
    speech_request: SpeechRequest,
    auth: Any = Depends(verify_request),
) -> StreamingResponse:
    current = _host()
    if current.tts_model is None:
        raise HTTPException(status_code=503, detail="TTS model is not available")

    configured_tts = settings.get("tts", {})
    requested_model = speech_request.model or configured_tts.get("provider")
    if requested_model and requested_model != configured_tts.get("provider"):
        raise HTTPException(status_code=404, detail=f"TTS model not loaded: {requested_model}")

    voice = speech_request.voice or configured_tts.get("voice", "nova")
    response_format = speech_request.response_format or configured_tts.get("response_format", "wav")

    try:
        pcm = current.tts_model.synthesize(speech_request.input, voice)
        if response_format == "pcm":
            return StreamingResponse(_stream_audio(request, pcm, include_wav_header=False), media_type="audio/pcm")
        return StreamingResponse(_stream_audio(request, pcm, include_wav_header=True), media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
