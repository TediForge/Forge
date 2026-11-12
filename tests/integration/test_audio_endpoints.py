import asyncio
import base64
from types import SimpleNamespace

import httpx

from src.api import app
from src.core.security.identity import Principal


class AuthenticatedASGI:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["principal"] = Principal("user-1", "tenant-a")
        await self.application(scope, receive, send)


class RecordingToolExecutor:
    def __init__(self):
        self.calls = []

    async def executeAsync(self, call):
        self.calls.append(call)
        if call["name"] == "transcribe":
            return {"success": True, "text": "hello", "language": "en", "segments": []}
        return {
            "success": True,
            "mediaData": base64.b64encode(b"speech-bytes").decode("ascii"),
            "mimeType": "audio/mpeg",
            "fileSizeBytes": len(b"speech-bytes"),
        }


def test_authenticated_batch_audio_routes_reuse_speech_tools():
    async def run():
        old_engine = getattr(app.state, "engine", None)
        tools = RecordingToolExecutor()
        app.state.engine = SimpleNamespace(toolExecutor=tools)
        transport = httpx.ASGITransport(app=AuthenticatedASGI(app))
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                transcription = await client.post(
                    "/v1/audio/transcriptions",
                    files={"file": ("voice.wav", b"wav-data", "audio/wav")},
                    data={"language": "en", "response_format": "json"},
                )
                assert transcription.status_code == 200
                assert transcription.json() == {"text": "hello", "language": "en"}
                assert tools.calls[0]["name"] == "transcribe"
                assert tools.calls[0]["arguments"]["mimeType"] == "audio/wav"

                speech = await client.post("/v1/audio/speech", json={"input": "hello"})
                assert speech.status_code == 200
                assert speech.content == b"speech-bytes"
                assert speech.headers["content-type"] == "audio/wav"
                assert tools.calls[1]["name"] == "speak"
                assert tools.calls[1]["arguments"]["text"] == "hello"
        finally:
            if old_engine is None:
                del app.state.engine
            else:
                app.state.engine = old_engine

    asyncio.run(run())


def test_audio_endpoints_require_a_principal():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/audio/speech",
                json={"input": "hello"},
            )
        assert response.status_code == 401

    asyncio.run(run())
