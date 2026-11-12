import asyncio
import sys
from contextlib import nullcontext
from types import SimpleNamespace

from src.core.models import huggingface
from src.core.models.huggingface import HuggingFaceInference
from src.core.models.registry import MODELS, ModelDefinition


def test_model_registry_declares_runtime_for_every_model():
    assert set(MODELS) == {
        "text", "image", "audio", "transcription", "video",
        "vision", "document", "data", "embedding",
    }
    assert all(model.runtime for model in MODELS.values())
    assert all(isinstance(model, ModelDefinition) for model in MODELS.values())
    assert MODELS["text"].hf_repo == "Qwen/Qwen2.5-0.5B-Instruct"
    assert MODELS["transcription"].hf_repo == "Systran/faster-whisper-small"
    assert MODELS["embedding"].hf_repo == "sentence-transformers/all-MiniLM-L6-v2"
    assert MODELS["audio"].allow_patterns == (
        "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    )


def test_embedding_downloads_snapshot_and_reuses_then_reloads_local_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(huggingface, "MODEL_CACHE_DIR", tmp_path)
    downloadCalls = []

    def download(**kwargs):
        downloadCalls.append(kwargs)
        path = tmp_path / f"snapshot-{len(downloadCalls)}"
        path.mkdir()
        return str(path)

    class SentenceTransformer:
        def __init__(self, path, device):
            self.path = path
            self.device = device

        def encode(self, inputs, convert_to_numpy):
            assert inputs == ["hello", "Forge"]
            assert convert_to_numpy is True
            return [[0.1, 0.2], [0.3, 0.4]]

    monkeypatch.setattr(huggingface, "snapshot_download", download)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=SentenceTransformer),
    )
    provider = HuggingFaceInference(model="embedding", token="hf-download-token")
    otherProvider = HuggingFaceInference(model="embedding")
    assert provider._runtime is None and otherProvider._runtime is None

    result = asyncio.run(provider.embed(["hello", "Forge"]))
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert len(downloadCalls) == 1
    assert downloadCalls[0]["repo_id"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert downloadCalls[0]["token"] == "hf-download-token"
    assert downloadCalls[0]["local_dir"].endswith("Embed")

    asyncio.run(provider.close())
    asyncio.run(provider.embed(["hello", "Forge"]))
    assert len(downloadCalls) == 2
    assert otherProvider._runtime is None


def test_model_defaults_are_source_controlled_and_registry_controls_download(monkeypatch, tmp_path):
    monkeypatch.setattr(huggingface, "MODEL_CACHE_DIR", tmp_path)
    monkeypatch.setenv("FORGE_MODEL_CACHE", str(tmp_path / "ignored-cache"))
    monkeypatch.setenv("FORGE_MODEL_DEVICE", "cuda")
    monkeypatch.setenv("FORGE_STT_MODEL", "ignored/model")
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        path = tmp_path / "Voice"
        path.mkdir()
        return str(path)

    monkeypatch.setattr(huggingface, "snapshot_download", download)
    provider = HuggingFaceInference(model="audio")

    assert provider._device == "cpu"
    assert provider._cacheDir == tmp_path
    provider._localPath()
    assert calls == [{
        "repo_id": "rhasspy/piper-voices",
        "local_dir": str(tmp_path / "Voice"),
        "token": None,
        "allow_patterns": [
            "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
            "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        ],
    }]


def test_text_generation_uses_local_transformers_and_registry_parameters(monkeypatch, tmp_path):
    observed = {}

    class InputIds(list):
        shape = (1, 2)

    class Tokens(dict):
        def to(self, device):
            observed["device"] = device
            return self

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, path, local_files_only):
            observed["tokenizer"] = (path, local_files_only)
            return cls()

        def __call__(self, prompt, return_tensors):
            observed["prompt"] = (prompt, return_tensors)
            return Tokens(input_ids=InputIds([[1, 2]]))

        def decode(self, tokens, skip_special_tokens):
            assert skip_special_tokens is True
            return "Forge response<END>ignored"

    class Model:
        @classmethod
        def from_pretrained(cls, path, local_files_only):
            observed["model"] = (path, local_files_only)
            return cls()

        def to(self, device):
            observed["modelDevice"] = device

        def eval(self):
            observed["eval"] = True

        def generate(self, **kwargs):
            observed["generation"] = kwargs
            return [[1, 2, 3]]

    monkeypatch.setattr(huggingface, "snapshot_download", lambda **kwargs: str(tmp_path))
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoTokenizer=Tokenizer, AutoModelForCausalLM=Model),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext))

    monkeypatch.setattr(huggingface, "MODEL_CACHE_DIR", tmp_path)
    provider = HuggingFaceInference(model="text")
    result = asyncio.run(provider.generateText(
        "user: hello",
        max_new_tokens=12,
        stop="<END>",
    ))
    assert result == "Forge response"
    assert observed["generation"]["max_new_tokens"] == 12
    assert observed["generation"]["temperature"] == 0.7
    assert observed["generation"]["top_p"] == 0.9
    assert observed["generation"]["do_sample"] is True
    assert "stop" not in observed["generation"]
    assert observed["tokenizer"] == (str(tmp_path), True)
    assert observed["model"] == (str(tmp_path), True)


def test_local_faster_whisper_runtime_transcribes_audio(monkeypatch, tmp_path):
    observed = {}

    class Segment:
        start = 0.25
        end = 1.5
        text = " local transcript"

    class WhisperModel:
        def __init__(self, path, **options):
            observed["load"] = (path, options)

        def transcribe(self, audioPath, **options):
            with open(audioPath, "rb") as audioFile:
                observed["audio"] = audioFile.read()
            observed["transcribe"] = options
            return iter([Segment()]), SimpleNamespace(language="en")

    monkeypatch.setattr(huggingface, "snapshot_download", lambda **kwargs: str(tmp_path))
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=WhisperModel))
    monkeypatch.setattr(huggingface, "MODEL_CACHE_DIR", tmp_path)
    provider = HuggingFaceInference(model="transcription")
    result = asyncio.run(provider.transcribe(
        b"audio bytes",
        "audio/wav",
        language="en",
        timestamps=True,
    ))
    assert result == {
        "text": "local transcript",
        "language": "en",
        "segments": [{"start": 0.25, "end": 1.5, "text": " local transcript"}],
    }
    assert observed["load"] == (
        str(tmp_path),
        {"device": "cpu", "device_index": 0, "compute_type": "int8"},
    )
    assert observed["audio"] == b"audio bytes"
    assert observed["transcribe"] == {"language": "en", "word_timestamps": True}


def test_local_image_runtime_loads_diffusers_pipeline(monkeypatch, tmp_path):
    observed = {}

    class Pipeline:
        def to(self, device):
            observed["device"] = device
            return self

        def __call__(self, **kwargs):
            observed["inference"] = kwargs
            return "local image result"

    class DiffusionPipeline:
        @classmethod
        def from_pretrained(cls, path, local_files_only):
            observed["load"] = (path, local_files_only)
            return Pipeline()

    monkeypatch.setitem(
        sys.modules,
        "diffusers",
        SimpleNamespace(DiffusionPipeline=DiffusionPipeline),
    )
    provider = HuggingFaceInference(model="image")
    pipeline = provider._loadRuntime(tmp_path)
    result = pipeline(prompt="sunrise", num_inference_steps=4)
    assert result == "local image result"
    assert observed == {
        "load": (str(tmp_path), True),
        "device": "cpu",
        "inference": {"prompt": "sunrise", "num_inference_steps": 4},
    }


def test_vision_registry_model_uses_vision_transformers_runtime(monkeypatch, tmp_path):
    observed = {}

    class Processor:
        @classmethod
        def from_pretrained(cls, path, local_files_only):
            observed["processor"] = (path, local_files_only)
            return cls()

    class Model:
        @classmethod
        def from_pretrained(cls, path, local_files_only):
            observed["model"] = (path, local_files_only)
            return cls()

        def to(self, device):
            observed["device"] = device

        def eval(self):
            observed["eval"] = True

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoProcessor=Processor, AutoModelForVision2Seq=Model),
    )
    runtime = HuggingFaceInference(model="vision")._loadRuntime(tmp_path)
    assert isinstance(runtime, tuple)
    assert observed == {
        "processor": (str(tmp_path), True),
        "model": (str(tmp_path), True),
        "device": "cpu",
        "eval": True,
    }
