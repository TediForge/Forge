import asyncio
import queue
import sys
from contextlib import nullcontext
from types import SimpleNamespace

from orchestrator.inference.backends.local import HuggingFaceInference
from orchestrator.inference.registry import MODELS, ModelDefinition
from orchestrator.inference.sources import huggingface as huggingface_source


def test_model_registry_declares_runtime_for_every_model():
    assert set(MODELS) == {
        "text", "image", "audio", "transcription", "video",
        "vision", "document", "data", "embedding",
    }
    assert all(model.runtime for model in MODELS.values())
    assert all(isinstance(model, ModelDefinition) for model in MODELS.values())
    assert MODELS["text"].locator == "Qwen/Qwen2.5-0.5B-Instruct"
    assert MODELS["transcription"].locator == "Systran/faster-whisper-small"
    assert MODELS["embedding"].locator == "sentence-transformers/all-MiniLM-L6-v2"
    assert MODELS["audio"].allow_patterns == (
        "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    )


def test_huggingface_source_resolves_catalog_locator_with_token_and_allow_patterns(monkeypatch, tmp_path):
    downloadCalls = []

    def download(**kwargs):
        downloadCalls.append(kwargs)
        return str(tmp_path)

    monkeypatch.setattr(huggingface_source, "snapshot_download", download)
    source = huggingface_source.HuggingFaceSource(
        cache_dir=tmp_path,
        token="hf-download-token",
        allow_patterns=MODELS["audio"].allow_patterns,
    )
    path = asyncio.run(source.resolve(MODELS["audio"].locator))

    assert path == tmp_path
    assert downloadCalls == [{
        "repo_id": MODELS["audio"].locator,
        "local_dir": str(tmp_path),
        "token": "hf-download-token",
        "allow_patterns": list(MODELS["audio"].allow_patterns),
    }]


def test_embedding_runtime_loads_only_after_source_path_is_supplied(monkeypatch, tmp_path):
    class SentenceTransformer:
        def __init__(self, path, device):
            self.path = path
            self.device = device

        def encode(self, inputs, convert_to_numpy):
            assert inputs == ["hello", "Forge"]
            assert convert_to_numpy is True
            return [[0.1, 0.2], [0.3, 0.4]]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=SentenceTransformer),
    )
    provider = HuggingFaceInference(model="embedding", model_path=tmp_path)
    otherProvider = HuggingFaceInference(model="embedding", model_path=tmp_path)
    assert provider._runtime is None and otherProvider._runtime is None

    result = asyncio.run(provider.embed(["hello", "Forge"]))
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert provider._runtime.path == str(tmp_path)
    assert otherProvider._runtime is None


def test_local_runtime_requires_an_explicit_resolved_path():
    provider = HuggingFaceInference(model="audio")
    try:
        provider._localPath()
    except RuntimeError as exc:
        assert "resolved by an inference source" in str(exc)
    else:
        raise AssertionError("A local model path must be resolved by an inference source.")


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

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoTokenizer=Tokenizer, AutoModelForCausalLM=Model),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext))

    provider = HuggingFaceInference(model="text", model_path=tmp_path)
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


def test_text_streaming_yields_provider_chunks_without_retokenizing(monkeypatch, tmp_path):
    class Tokens(dict):
        def to(self, device):
            return self

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, path, local_files_only):
            return cls()

        def __call__(self, text=None, return_tensors=None, **_kwargs):
            return Tokens(input_ids=[[1, 2]])

        def decode(self, tokens, skip_special_tokens):
            return "unused"

    class Streamer:
        def __init__(self, *_args, timeout, **_kwargs):
            self.items = queue.Queue()
            self.timeout = timeout

        def __iter__(self):
            return self

        def __next__(self):
            item = self.items.get(timeout=self.timeout)
            if item is None:
                raise StopIteration
            return item

        def put(self, item):
            self.items.put(item)

        def end(self):
            self.items.put(None)

    class StoppingCriteria:
        pass

    class StoppingCriteriaList(list):
        pass

    class Model:
        @classmethod
        def from_pretrained(cls, path, local_files_only):
            return cls()

        def to(self, device):
            return None

        def eval(self):
            return None

        def generate(self, **kwargs):
            kwargs["streamer"].put("token ")
            kwargs["streamer"].put("stream")
            kwargs["streamer"].end()


    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=Tokenizer,
            AutoModelForCausalLM=Model,
            StoppingCriteria=StoppingCriteria,
            StoppingCriteriaList=StoppingCriteriaList,
            TextIteratorStreamer=Streamer,
        ),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext))

    async def collect():
        provider = HuggingFaceInference(model="text", model_path=tmp_path)
        return [chunk async for chunk in provider.streamText("prompt", max_new_tokens=8)]

    assert asyncio.run(collect()) == ["token ", "stream"]


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

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=WhisperModel))
    provider = HuggingFaceInference(model="transcription", model_path=tmp_path)
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
    provider = HuggingFaceInference(model="image", model_path=tmp_path)
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
    runtime = HuggingFaceInference(model="vision", model_path=tmp_path)._loadRuntime(tmp_path)
    assert isinstance(runtime, tuple)
    assert observed == {
        "processor": (str(tmp_path), True),
        "model": (str(tmp_path), True),
        "device": "cpu",
        "eval": True,
    }
