"""Stable model resolution and inference execution boundary."""

import asyncio
import inspect
import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

from orchestrator.inference.backends.base import Backend, BackendUnavailableError
from orchestrator.inference.backends.diffusers import DiffusersBackend
from orchestrator.inference.backends.piper import PiperBackend
from orchestrator.inference.backends.transformers import TransformersBackend
from orchestrator.inference.backends.whisper import WhisperBackend
from orchestrator.inference.protocols import InferenceRequest, InferenceResponse
from orchestrator.inference.registry import MODEL_REGISTRY, ModelDefinition, ModelRegistration
from orchestrator.inference.runtime.cache import RuntimeCache
from orchestrator.inference.runtime.devices import validate_device
from orchestrator.inference.sources import ArtifactStoreSource, HuggingFaceSource, LocalPathSource
from orchestrator.inference.sources.base import Source, SourceError
from orchestrator.settings import Settings, get_settings


logger = logging.getLogger(__name__)
SourceFactory = Callable[[ModelRegistration], Source]
BackendFactory = Callable[[ModelRegistration, Path, Settings], Backend]


def _default_sources(entry: ModelRegistration, settings: Settings) -> Source:
    config = settings.inference_model_sources.get(entry.model_id, {})
    source_type = config.get("type", entry.source_type)
    locator = config.get("locator", entry.locator)
    if source_type == "huggingface":
        patterns = entry.definition.allow_patterns
        return HuggingFaceSource(
            cache_dir=settings.model_cache_dir / entry.model_id,
            allow_patterns=patterns,
        )
    if source_type == "localpath":
        return LocalPathSource()
    if source_type == "artifacts":
        return ArtifactStoreSource()
    raise SourceError(f"Unknown source type '{source_type}' for model '{entry.model_id}'.")


def _create_transformers(entry: ModelRegistration, path: Path, settings: Settings) -> Backend:
    return TransformersBackend(entry.definition, path, device=validate_device(settings.inference_device))


def _create_piper(entry: ModelRegistration, path: Path, settings: Settings) -> Backend:
    return PiperBackend(entry.definition, path, device=validate_device(settings.inference_device))


def _create_whisper(entry: ModelRegistration, path: Path, settings: Settings) -> Backend:
    return WhisperBackend(entry.definition, path, device=validate_device(settings.inference_device))


def _create_diffusers(entry: ModelRegistration, path: Path, settings: Settings) -> Backend:
    return DiffusersBackend(entry.definition, path, device=validate_device(settings.inference_device))


class InferenceGateway:
    def __init__(
        self,
        registry: Mapping[str, ModelRegistration] = MODEL_REGISTRY,
        source_factory: SourceFactory | None = None,
        backend_factories: Mapping[str, BackendFactory] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.registry = registry
        self.settings = settings or get_settings()
        self.source_factory = source_factory or (
            lambda entry: _default_sources(entry, self.settings)
        )
        self.backend_factories = dict(backend_factories or {
            "transformers": _create_transformers,
            "piper": _create_piper,
            "whisper": _create_whisper,
            "diffusers": _create_diffusers,
        })
        self._cache: RuntimeCache[Backend] = RuntimeCache()
        self._load_times: dict[tuple[str, str], float] = {}
        self._providers: dict[str, _ProviderFacade] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(self.settings.inference_max_concurrency)
        self._closed = False

    def _registration(self, model_id: str | ModelDefinition) -> ModelRegistration:
        if not isinstance(model_id, str):
            definition = model_id
            for entry in self.registry.values():
                if entry.definition is definition or entry.definition.model_id == definition.model_id:
                    return entry
            raise KeyError(f"Unknown inference model: {definition.model_id}")
        try:
            return self.registry[model_id]
        except KeyError:
            normalized = model_id.casefold()
            for key, entry in self.registry.items():
                if normalized in {
                    key.casefold(),
                    entry.model_id.casefold(),
                    entry.definition.model_id.casefold(),
                    entry.locator.casefold(),
                }:
                    return entry
            raise KeyError(f"Unknown inference model: {model_id}")

    def _backend_id(self, entry: ModelRegistration, modality: str) -> str:
        configured = self.settings.inference_model_backends.get(entry.model_id)
        if configured:
            return configured
        return self.settings.inference_default_backends.get(modality, entry.default_backend)

    async def resolve(self, model_id: str, modality: str) -> tuple[Backend, float]:
        if self._closed:
            raise RuntimeError("Inference gateway is closed")
        entry = self._registration(model_id)
        if modality not in entry.modalities:
            raise ValueError(f"Model '{entry.model_id}' does not support modality '{modality}'.")
        backend_id = self._backend_id(entry, modality)
        factory = self.backend_factories.get(backend_id)
        if factory is None:
            raise BackendUnavailableError(
                f"Backend '{backend_id}' is configured for model '{entry.model_id}' but is unavailable. "
                "Install or configure that optional backend before serving requests."
            )
        cached = self._cache.get(entry.model_id, backend_id)
        if cached is not None:
            return cached, self._load_times[(entry.model_id, backend_id)]
        async with self._lock:
            cached = self._cache.get(entry.model_id, backend_id)
            if cached is not None:
                return cached, self._load_times[(entry.model_id, backend_id)]
            started = time.perf_counter()
            source = self.source_factory(entry)
            source_config = self.settings.inference_model_sources.get(entry.model_id, {})
            path = await source.resolve(source_config.get("locator", entry.locator))
            backend = factory(entry, path, self.settings)
            self._cache.set(entry.model_id, backend_id, backend)
            load_ms = (time.perf_counter() - started) * 1000
            self._load_times[(entry.model_id, backend_id)] = load_ms
            return backend, load_ms

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        backend, load_ms = await self.resolve(request.model_id, request.modality)
        operation = {
            "text": backend.generate,
            "embedding": backend.embed,
            "transcription": backend.transcribe,
            "speech": backend.synthesize,
            "image_gen": backend.generate_image,
            "vision": backend.generate,
            "video": backend.generate,
        }.get(request.modality)
        if operation is None:
            raise ValueError(f"Unsupported inference modality: {request.modality}")
        started = time.perf_counter()
        async with self._semaphore:
            output = await asyncio.wait_for(
                operation(request),
                timeout=self.settings.inference_timeout_seconds,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        result = InferenceResponse(
            model_id=request.model_id,
            modality=request.modality,
            backend_id=backend.backend_id,
            output=output,
            load_ms=load_ms,
            latency_ms=latency_ms,
        )
        logger.info(
            "inference.complete",
            extra={
                "model_id": request.model_id,
                "backend_id": backend.backend_id,
                "modality": request.modality,
                "load_ms": round(load_ms, 3),
                "latency_ms": round(latency_ms, 3),
            },
        )
        return result

    def get(self, model: str | ModelDefinition) -> Any:
        """Return a lazy provider facade for compatibility with existing dispatchers."""
        entry = self._registration(model)
        provider = self._providers.get(entry.model_id)
        if provider is None:
            provider = _ProviderFacade(self, entry)
            self._providers[entry.model_id] = provider
        return provider

    def readiness(self, required_models: tuple[str, ...] = ("text",)) -> dict[str, Any]:
        missing: list[str] = []
        cache_root = self.settings.model_cache_dir.expanduser().resolve()
        for model_id in required_models:
            entry = self._registration(model_id)
            backend_id = self._backend_id(entry, entry.modalities[0])
            if self._cache.get(entry.model_id, backend_id) is not None:
                continue
            local_path = (cache_root / entry.definition.model_id).resolve()
            if not local_path.is_dir():
                missing.append(entry.definition.model_id)
                continue
            config_present = (local_path / "config.json").is_file()
            weights_present = any(
                path.is_file()
                for pattern in ("*.safetensors", "pytorch_model*.bin")
                for path in local_path.rglob(pattern)
            )
            if not config_present or not weights_present:
                missing.append(entry.definition.model_id)
        return {"status": "ready" if not missing else "not_ready", "missingModels": missing}

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        backend, _ = await self.resolve(request.model_id, request.modality)
        async with self._semaphore:
            iterator = backend.stream(request)
            if inspect.isawaitable(iterator):
                iterator = await iterator
            async for chunk in iterator:
                yield chunk

    async def health(self) -> bool:
        results = await asyncio.gather(
            *(backend.health() for backend in self._cache.values()),
            return_exceptions=True,
        )
        errors = [value for value in results if isinstance(value, BaseException)]
        if errors:
            raise ExceptionGroup("Inference backend health checks failed", errors)
        return all(value is True for value in results)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        results = await asyncio.gather(
            *(backend.close() for backend in self._cache.values()),
            return_exceptions=True,
        )
        errors = [value for value in results if isinstance(value, BaseException)]
        if errors:
            raise ExceptionGroup("Inference backends failed to close", errors)
        self._cache.clear()
        self._providers.clear()


class _ProviderFacade:
    def __init__(self, gateway: InferenceGateway, entry: ModelRegistration) -> None:
        self.gateway = gateway
        self.entry = entry

    async def generateText(self, prompt: str, **parameters: Any) -> str:
        result = await self.gateway.infer(InferenceRequest(
            self.entry.model_id, "text", prompt, parameters,
        ))
        return str(result.output)

    async def streamText(self, prompt: str, **parameters: Any) -> AsyncIterator[str]:
        async for part in self.gateway.stream(InferenceRequest(
            self.entry.model_id, "text", prompt, parameters,
        )):
            yield part

    async def generateImage(self, prompt: str, **parameters: Any) -> Any:
        result = await self.gateway.infer(InferenceRequest(
            self.entry.model_id, "image_gen", prompt, parameters,
        ))
        return result.output

    async def embed(self, inputs: Any) -> Any:
        result = await self.gateway.infer(InferenceRequest(
            self.entry.model_id, "embedding", inputs,
        ))
        return result.output

    async def transcribe(
        self,
        audioBytes: bytes,
        mimeType: str,
        language: str | None = None,
        timestamps: bool = False,
    ) -> Any:
        result = await self.gateway.infer(InferenceRequest(
            self.entry.model_id,
            "transcription",
            audioBytes,
            {"mimeType": mimeType, "language": language, "timestamps": timestamps},
        ))
        return result.output

    async def synthesize(self, text: str, **parameters: Any) -> Any:
        result = await self.gateway.infer(InferenceRequest(
            self.entry.model_id, "speech", text, parameters,
        ))
        return result.output

    async def analyze_image(self, *, prompt: str, system_prompt: str, images: list[Any]) -> Any:
        result = await self.gateway.infer(InferenceRequest(
            self.entry.model_id,
            "vision",
            {"prompt": prompt, "system_prompt": system_prompt, "images": images},
        ))
        return result.output

    async def close(self) -> None:
        return None
