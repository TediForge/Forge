import asyncio
import base64
import sys
import wave
from types import SimpleNamespace

from src.core.models.adapters.base import DispatcherError
from src.core.models.adapters.stt import SttDispatcher
from src.core.models.adapters.voice import VoiceDispatcher
from src.core.models.huggingface import HuggingFaceInference
from src.tools.definitions import speak, transcribe
from src.tools.executor import ToolExecutor
from src.tools.registry import create_default_registry


def test_speech_tools_are_registered_with_one_image_and_video_schema():
    registry = create_default_registry()
    assert {"image", "video", "transcribe", "speak", "fetch", "translate", "pdf", "generate", "weather"} <= set(registry.names())
    assert not {"code", "shell", "browse"} & set(registry.names())
    assert "title" not in registry.names()
    assert not {"info", "resize", "analyze", "ocr", "detect", "sample", "keyframe"} & set(registry.names())
    assert registry.get("image")["function"]["parameters"]["properties"]["operation"]["enum"]
    assert registry.get("video")["function"]["parameters"]["properties"]["operation"]["enum"]


def test_transcribe_uses_injected_forge_dispatcher_and_returns_timestamps():
    audio = base64.b64encode(b"RIFF-audio").decode("ascii")

    class Dispatcher:
        async def transcribe(self, **kwargs):
            assert kwargs == {
                "audioBytes": b"RIFF-audio",
                "mimeType": "audio/wav",
                "language": "en",
                "timestamps": True,
            }
            return {"text": "hello", "language": "en", "segments": [{"start": 0, "end": 1, "text": "hello"}]}

    result = asyncio.run(transcribe.handle_transcribe(
        "audio", audio, "audio/wav", language="en", timestamps=True, dispatcher=Dispatcher(),
    ))
    assert result["success"] is True
    assert result["text"] == "hello"
    assert result["segments"] == [{"start": 0, "end": 1, "text": "hello"}]


def test_transcribe_validation_and_dispatcher_errors():
    class FailedDispatcher:
        async def transcribe(self, **kwargs):
            raise DispatcherError("model unavailable")

    badData = asyncio.run(transcribe.handle_transcribe("audio", "not-base64", "audio/wav", dispatcher=FailedDispatcher()))
    invalidModel = asyncio.run(transcribe.handle_transcribe(
        "audio",
        base64.b64encode(b"audio").decode("ascii"),
        "audio/wav",
        model="forge-stt",
        dispatcher=FailedDispatcher(),
    ))
    failed = asyncio.run(transcribe.handle_transcribe(
        "audio",
        base64.b64encode(b"audio").decode("ascii"),
        "audio/wav",
        dispatcher=FailedDispatcher(),
    ))
    assert badData["errorCode"] == "INVALID_MEDIA"
    assert invalidModel["errorCode"] == "INVALID_MODEL"
    assert failed["errorCode"] == "PROVIDER_ERROR"


def test_speak_uses_injected_forge_dispatcher_and_returns_inline_audio():
    audioBytes = b"spoken audio"

    class Dispatcher:
        async def synthesize(self, **kwargs):
            assert kwargs == {
                "text": "Hello",
                "voice": "default",
                "format": "wav",
                "speed": 1.0,
                "instructions": None,
            }
            return audioBytes

    result = asyncio.run(speak.handle_speak("text", "Hello", dispatcher=Dispatcher()))
    assert result["success"] is True
    assert base64.b64decode(result["mediaData"]) == audioBytes
    assert result["mimeType"] == "audio/wav"
    assert result["fileSizeBytes"] == len(audioBytes)


def test_speak_rejects_unsupported_options_and_dispatcher_failures():
    class FailedDispatcher:
        async def synthesize(self, **kwargs):
            raise DispatcherError("model unavailable")

    noInstructions = asyncio.run(speak.handle_speak(
        "text", "Hello", instructions="whisper", dispatcher=FailedDispatcher(),
    ))
    failed = asyncio.run(speak.handle_speak("text", "Hello", dispatcher=FailedDispatcher()))
    assert noInstructions["errorCode"] == "UNSUPPORTED_OPTION"
    assert failed["errorCode"] == "PROVIDER_ERROR"
    assert asyncio.run(speak.handle_speak(
        "text", "Hello", format="mp3", dispatcher=FailedDispatcher(),
    ))["errorCode"] == "INVALID_FORMAT"


def test_tool_executor_injects_dispatchers_without_exposing_arguments():
    class SpeechDispatcher:
        async def synthesize(self, **kwargs):
            return b"local audio"

    class TranscriptionDispatcher:
        async def transcribe(self, **kwargs):
            return {"text": "local transcript", "language": "en", "segments": []}

    executor = ToolExecutor(toolDependencies={
        "speak": {"dispatcher": SpeechDispatcher()},
        "transcribe": {"dispatcher": TranscriptionDispatcher()},
    })
    speech = asyncio.run(executor.executeAsync({
        "name": "speak",
        "arguments": {"operation": "text", "text": "hello"},
    }))
    transcription = asyncio.run(executor.executeAsync({
        "name": "transcribe",
        "arguments": {
            "operation": "audio",
            "mediaData": base64.b64encode(b"audio").decode("ascii"),
            "mimeType": "audio/wav",
        },
    }))
    assert base64.b64decode(speech["mediaData"]) == b"local audio"
    assert transcription["text"] == "local transcript"


def test_stt_dispatcher_maps_faster_whisper_results_and_cleans_temp_audio():
    observed = {}

    class Segment:
        start = 1.25
        end = 2.5
        text = " hello"

    class Model:
        def transcribe(self, path, **kwargs):
            with open(path, "rb") as audio_file:
                observed["bytes"] = audio_file.read()
            observed["kwargs"] = kwargs
            return iter([Segment()]), type("Info", (), {"language": "en"})()

    provider = HuggingFaceInference(model="transcription")
    result = provider._transcribeLocal(Model(), b"audio bytes", ".wav", "en", True)
    assert observed["bytes"] == b"audio bytes"
    assert observed["kwargs"] == {"language": "en", "word_timestamps": True}
    assert result == {
        "text": "hello",
        "language": "en",
        "segments": [{"start": 1.25, "end": 2.5, "text": " hello"}],
    }


def test_stt_dispatcher_delegates_to_local_model_runtime():
    class LocalRuntime:
        async def transcribe(self, **kwargs):
            return {"text": "local transcript", "language": "en", "segments": []}

    result = asyncio.run(SttDispatcher(provider=LocalRuntime()).transcribe(
        audioBytes=b"audio",
        mimeType="audio/wav",
    ))
    assert result["text"] == "local transcript"


def test_voice_dispatcher_returns_piper_wav_bytes():
    class PiperProvider:
        async def synthesize(self, **kwargs):
            return b"piper output"

    result = asyncio.run(VoiceDispatcher(provider=PiperProvider()).synthesize("hello"))
    assert result == b"piper output"


def test_voice_dispatcher_loads_local_piper_model_and_returns_pcm(monkeypatch, tmp_path):
    modelPath = tmp_path / "voice.onnx"
    modelPath.write_bytes(b"model")
    observed = {}

    class PiperVoice:
        @classmethod
        def load(cls, path, use_cuda):
            observed["model"] = (path, use_cuda)
            return cls()

        def synthesize_wav(self, text, wav, syn_config):
            observed["synthesis"] = (text, syn_config.length_scale)
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x01\x00\x02\x00")

    class SynthesisConfig:
        def __init__(self, length_scale):
            self.length_scale = length_scale

    monkeypatch.setattr(HuggingFaceInference, "_localPath", lambda self: modelPath)
    monkeypatch.setitem(
        sys.modules,
        "piper",
        SimpleNamespace(PiperVoice=PiperVoice, SynthesisConfig=SynthesisConfig),
    )
    result = asyncio.run(VoiceDispatcher().synthesize("hello", format="pcm", speed=2.0))
    assert result == b"\x01\x00\x02\x00"
    assert observed == {
        "model": (str(modelPath), False),
        "synthesis": ("hello", 0.5),
    }


def test_stt_dispatcher_loads_configured_faster_whisper_model(monkeypatch, tmp_path):
    observed = {}

    class WhisperModel:
        def __init__(self, modelName, **options):
            observed.update(modelName=modelName, **options)

    modelPath = tmp_path / "whisper"
    modelPath.mkdir()
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=WhisperModel))
    model = HuggingFaceInference(model="transcription")._loadRuntime(modelPath)
    assert isinstance(model, WhisperModel)
    assert observed == {
        "modelName": str(modelPath),
        "device": "cpu",
        "device_index": 0,
        "compute_type": "int8",
    }


def test_no_external_openai_client_or_http_in_tool_definitions():
    for module in (speak, transcribe):
        source = open(module.__file__, encoding="utf-8").read()
        assert "httpx" not in source
        assert "FORGE_OPENAI" not in source
        assert "api.openai.com" not in source
