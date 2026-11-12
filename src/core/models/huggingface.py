"""Download Hugging Face model weights and run inference on this machine."""

import asyncio
import io
import os
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download

from src.core.models.registry import ModelDefinition, get_model


MODEL_CACHE_DIR = Path("data/models")
MODEL_DEVICE = "cpu"
TTS_DEVICE = "cpu"
STT_DEVICE = "cpu"
STT_COMPUTE_TYPE = "int8"


class HuggingFaceInference:
    """Lazily load a registry model from local weights and run its local runtime."""

    def __init__(
        self,
        model: str | ModelDefinition = "text",
        token: str | None = None,
    ) -> None:
        self.model = get_model(model) if isinstance(model, str) else model
        self._token = token if token is not None else os.getenv("HF_TOKEN") or None
        self._device = MODEL_DEVICE
        self._cacheDir = MODEL_CACHE_DIR
        self._runtime: Any | None = None
        self._runtimeLock = asyncio.Lock()
        self._inferenceLock = threading.Lock()

    async def _ensureLoaded(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        async with self._runtimeLock:
            if self._runtime is None:
                localPath = await asyncio.to_thread(self._localPath)
                self._runtime = await asyncio.to_thread(self._loadRuntime, localPath)
        return self._runtime

    def _localPath(self) -> Path:
        try:
            localDirectory = self._cacheDir / self.model.model_id
            localDirectory.parent.mkdir(parents=True, exist_ok=True)
            options: dict[str, Any] = {
                "repo_id": self.model.hf_repo,
                "local_dir": str(localDirectory),
                "token": self._token,
            }
            if self.model.allow_patterns is not None:
                options["allow_patterns"] = list(self.model.allow_patterns)
            path = snapshot_download(**options)
        except Exception as exc:
            raise RuntimeError("Could not download the configured model snapshot from Hugging Face Hub") from exc
        return Path(path)

    def _loadRuntime(self, localPath: Path) -> Any:
        if self._device != "cpu" and not (
            self._device == "cuda"
            or self._device.startswith("cuda:")
            and self._device[5:].isdigit()
        ):
            raise RuntimeError("Model device must be cpu or a CUDA device")
        try:
            if self.model.runtime == "transformers":
                from transformers import AutoModelForCausalLM, AutoTokenizer

                tokenizer = AutoTokenizer.from_pretrained(str(localPath), local_files_only=True)
                model = AutoModelForCausalLM.from_pretrained(str(localPath), local_files_only=True)
                model.to(self._device)
                model.eval()
                return tokenizer, model
            if self.model.runtime == "vision-transformers":
                from transformers import AutoModelForVision2Seq, AutoProcessor

                processor = AutoProcessor.from_pretrained(str(localPath), local_files_only=True)
                model = AutoModelForVision2Seq.from_pretrained(str(localPath), local_files_only=True)
                model.to(self._device)
                model.eval()
                return processor, model
            if self.model.runtime == "sentence-transformers":
                from sentence_transformers import SentenceTransformer

                return SentenceTransformer(str(localPath), device=self._device)
            if self.model.runtime == "diffusers":
                from diffusers import DiffusionPipeline

                return DiffusionPipeline.from_pretrained(str(localPath), local_files_only=True).to(self._device)
            if self.model.runtime == "faster-whisper":
                from faster_whisper import WhisperModel

                sttDevice = STT_DEVICE.casefold()
                if sttDevice == "cpu":
                    device, deviceIndex = "cpu", 0
                elif sttDevice == "cuda":
                    device, deviceIndex = "cuda", 0
                elif sttDevice.startswith("cuda:") and sttDevice[5:].isdigit():
                    device, deviceIndex = "cuda", int(sttDevice[5:])
                else:
                    raise RuntimeError("Speech-to-text device must be cpu, cuda, or cuda:<index>")
                return WhisperModel(
                    str(localPath),
                    device=device,
                    device_index=deviceIndex,
                    compute_type=STT_COMPUTE_TYPE,
                )
            if self.model.runtime == "tts":
                from piper import PiperVoice

                voicePath = self._piperModelPath(localPath)
                ttsDevice = TTS_DEVICE.casefold()
                if ttsDevice not in {"cpu", "cuda"}:
                    raise RuntimeError("Text-to-speech device must be cpu or cuda")
                useCuda = ttsDevice == "cuda"
                return PiperVoice.load(str(voicePath), use_cuda=useCuda)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Could not load the local {self.model.runtime} runtime") from exc
        raise RuntimeError(f"Unsupported local model runtime: {self.model.runtime}")

    @staticmethod
    def _piperModelPath(localPath: Path) -> Path:
        if localPath.is_file() and localPath.suffix.casefold() == ".onnx":
            return localPath
        if localPath.is_dir():
            candidates = sorted(localPath.rglob("*.onnx"))
            if len(candidates) == 1:
                return candidates[0]
        raise RuntimeError("Piper model snapshot must contain exactly one ONNX voice file")

    async def embed(self, inputs: str | list[str]) -> list[list[float]]:
        if self.model.runtime != "sentence-transformers":
            raise RuntimeError("Selected model does not support local text embeddings")
        runtime = await self._ensureLoaded()
        values = await asyncio.to_thread(self._encodeLocal, runtime, inputs)
        if hasattr(values, "tolist"):
            values = values.tolist()
        if values and isinstance(values[0], (int, float)):
            values = [values]
        if not isinstance(values, list):
            raise RuntimeError("Local embedding model returned an invalid result")
        return values

    def _encodeLocal(self, runtime: Any, inputs: str | list[str]) -> Any:
        with self._inferenceLock:
            return runtime.encode(inputs, convert_to_numpy=True)

    async def generateText(self, prompt: str, **parameters: Any) -> str:
        if self.model.runtime not in {"transformers", "vision-transformers"}:
            raise RuntimeError("Selected model does not support local text generation")
        runtime = await self._ensureLoaded()
        return await asyncio.to_thread(self._generateTextLocal, runtime, prompt, parameters)

    def _generateTextLocal(
        self,
        runtime: tuple[Any, Any],
        prompt: str,
        parameters: dict[str, Any],
    ) -> str:
        merged = {**dict(self.model.parameters), **parameters}
        maxTokens = merged.get("max_new_tokens", merged.get("maxTokens", 4096))
        temperature = float(merged.get("temperature", 0.7))
        topP = float(merged.get("top_p", merged.get("topP", 0.9)))
        stop = merged.get("stop")
        options: dict[str, Any] = {
            "max_new_tokens": maxTokens,
            "do_sample": temperature > 0,
        }
        if temperature > 0:
            options.update(temperature=temperature, top_p=topP)

        if self.model.runtime == "vision-transformers":
            processor, model = runtime
            inputs = processor(text=prompt, return_tensors="pt")
            if hasattr(inputs, "to"):
                inputs = inputs.to(self._device)
            inputIds = inputs["input_ids"]
            inputLength = int(inputIds.shape[-1])
            with self._inferenceLock:
                with self._inferenceMode():
                    output = model.generate(**dict(inputs), **options)
            generatedTokens = output[:, inputLength:]
            generated = processor.batch_decode(generatedTokens, skip_special_tokens=True)[0]
            return self._cleanGeneratedText(generated, stop)

        tokenizer, model = runtime
        tokens = tokenizer(prompt, return_tensors="pt")
        if hasattr(tokens, "to"):
            tokens = tokens.to(self._device)
        inputIds = tokens["input_ids"]
        inputLength = int(inputIds.shape[-1]) if hasattr(inputIds, "shape") else len(inputIds[0])
        inputFields = dict(tokens)
        with self._inferenceLock:
            with self._inferenceMode():
                output = model.generate(**inputFields, **options)
        generated = tokenizer.decode(output[0][inputLength:], skip_special_tokens=True).strip()
        return self._cleanGeneratedText(generated, stop)

    @staticmethod
    def _cleanGeneratedText(generated: str, stop: Any) -> str:
        generated = generated.strip()
        if isinstance(stop, str):
            stop = [stop]
        if isinstance(stop, list):
            stopTokens = [item for item in stop if isinstance(item, str) and item]
            if stopTokens:
                generated = generated[:min(
                    (generated.find(item) for item in stopTokens if item in generated),
                    default=len(generated),
                )].rstrip()
        if not generated:
            raise RuntimeError("Local text model returned an empty completion")
        return generated

    @staticmethod
    def _inferenceMode():
        import torch

        return torch.inference_mode()

    async def generateImage(self, prompt: str, **parameters: Any) -> Any:
        if self.model.runtime != "diffusers":
            raise RuntimeError("Selected model does not support local image generation")
        runtime = await self._ensureLoaded()
        options = {**dict(self.model.parameters), **parameters}
        return await asyncio.to_thread(self._generateImageLocal, runtime, prompt, options)

    def _generateImageLocal(self, runtime: Any, prompt: str, options: dict[str, Any]) -> Any:
        with self._inferenceLock:
            return runtime(prompt=prompt, **options)

    async def transcribe(
        self,
        audioBytes: bytes,
        mimeType: str,
        language: str | None = None,
        timestamps: bool = False,
    ) -> dict[str, Any]:
        if self.model.runtime != "faster-whisper":
            raise RuntimeError("Selected model does not support local speech transcription")
        suffix = {
            "audio/flac": ".flac",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".mp4",
            "audio/mpga": ".mpga",
            "audio/m4a": ".m4a",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/webm": ".webm",
        }.get(mimeType)
        if suffix is None:
            raise ValueError("Unsupported audio MIME type")
        runtime = await self._ensureLoaded()
        return await asyncio.to_thread(
            self._transcribeLocal, runtime, audioBytes, suffix, language, timestamps
        )

    def _transcribeLocal(
        self,
        runtime: Any,
        audioBytes: bytes,
        suffix: str,
        language: str | None,
        timestamps: bool,
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as audioFile:
            audioFile.write(audioBytes)
            audioPath = audioFile.name
        try:
            with self._inferenceLock:
                segmentsIterator, info = runtime.transcribe(
                    audioPath,
                    language=language,
                    word_timestamps=timestamps,
                )
                segmentsIterator = list(segmentsIterator)
            textParts = []
            segments = []
            for segment in segmentsIterator:
                textParts.append(segment.text)
                if timestamps:
                    segments.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text,
                    })
            return {
                "text": "".join(textParts).strip(),
                "language": getattr(info, "language", language),
                "segments": segments,
            }
        except Exception as exc:
            raise RuntimeError("Local faster-whisper transcription failed") from exc
        finally:
            try:
                Path(audioPath).unlink()
            except OSError as exc:
                raise RuntimeError("Could not remove temporary transcription audio") from exc

    async def synthesize(
        self,
        text: str,
        voice: str = "default",
        format: str = "wav",
        speed: float = 1.0,
        instructions: str | None = None,
    ) -> bytes:
        if self.model.runtime != "tts":
            raise RuntimeError("Selected model does not support local speech synthesis")
        if voice != "default":
            raise ValueError("Only the configured Piper voice is supported")
        if format not in {"wav", "pcm"}:
            raise ValueError("Piper supports only wav and pcm output")
        if instructions:
            raise ValueError("Piper does not support speech instructions")
        runtime = await self._ensureLoaded()
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not 0.25 <= speed <= 4.0:
            raise ValueError("Speech speed must be between 0.25 and 4.0")
        return await asyncio.to_thread(self._synthesizeLocal, runtime, text, format, speed)

    def _synthesizeLocal(self, runtime: Any, text: str, format: str, speed: float) -> bytes:
        try:
            from piper import SynthesisConfig

            output = tempfile.SpooledTemporaryFile()
            config = SynthesisConfig(length_scale=1.0 / speed)
            with self._inferenceLock:
                with wave.open(output, "wb") as wav:
                    runtime.synthesize_wav(text, wav, syn_config=config)
            output.seek(0)
            wavBytes = output.read()
            output.close()
            if format == "wav":
                return wavBytes
            with wave.open(io.BytesIO(wavBytes), "rb") as wav:
                if wav.getsampwidth() != 2:
                    raise ValueError("Piper output is not PCM16")
                return wav.readframes(wav.getnframes())
        except Exception as exc:
            raise RuntimeError("Local Piper speech synthesis failed") from exc

    async def close(self) -> None:
        async with self._runtimeLock:
            self._runtime = None
