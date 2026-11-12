import asyncio
import base64
import io
import wave
from types import SimpleNamespace

from orchestrator.api.v1.audio.sts.routes import StsSession
from orchestrator.security.identity import Principal


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


class SpeechToolExecutor:
    def __init__(self):
        self.calls = []

    async def executeAsync(self, call):
        self.calls.append(call)
        if call["name"] == "transcribe":
            wavBytes = base64.b64decode(call["arguments"]["mediaData"])
            with wave.open(io.BytesIO(wavBytes), "rb") as wav:
                assert wav.getframerate() == 16000
                assert wav.getnchannels() == 1
                assert wav.getsampwidth() == 2
            return {"success": True, "text": "hello"}
        output = b"a" * (32 * 1024 + 3)
        return {
            "success": True,
            "mediaData": base64.b64encode(output).decode("ascii"),
        }


def test_sts_session_runs_transcribe_engine_speak_pipeline_and_chunks_output():
    async def run():
        tools = SpeechToolExecutor()
        engine = SimpleNamespace(
            toolExecutor=tools,
            run=lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(
                content=[SimpleNamespace(type="text", text="spoken answer")],
            )),
        )
        websocket = FakeWebSocket()
        session = StsSession(engine, websocket, Principal("user-1", "tenant-a"))
        await session._runTurn(b"\x00\x00")
        return tools, websocket

    tools, websocket = asyncio.run(run())
    assert [call["name"] for call in tools.calls] == ["transcribe", "speak"]
    assert tools.calls[1]["arguments"]["format"] == "pcm"
    assert any(message["type"] == "transcript.final" and message["text"] == "hello" for message in websocket.messages)
    chunks = [message for message in websocket.messages if message["type"] == "audio.output"]
    assert len(chunks) == 2
    assert chunks[0]["last"] is False
    assert chunks[1]["last"] is True
    assert all(message["mimeType"] == "audio/pcm" for message in chunks)
    assert websocket.messages[-1]["type"] == "response.done"


def test_sts_cancel_stops_inflight_transcription():
    async def run():
        started = asyncio.Event()

        class BlockingTools:
            async def executeAsync(self, call):
                started.set()
                await asyncio.Event().wait()

        session = StsSession(
            SimpleNamespace(toolExecutor=BlockingTools()),
            FakeWebSocket(),
            Principal("user-1", "tenant-a"),
        )
        session.turnTask = asyncio.create_task(session._runTurn(b"\x00\x00"))
        await started.wait()
        await session._cancelTurn()
        return session

    session = asyncio.run(run())
    assert session.turnTask is None
    assert {"type": "response.done", "cancelled": True} in session.websocket.messages
