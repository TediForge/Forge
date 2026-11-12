"""Authenticated push-to-talk local speech-to-speech WebSocket route."""

import asyncio
import base64
import binascii
import io
import json
import logging
import re
import uuid
import wave
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.schemas.input import ExecutionMode
from src.core.security.identity import Principal
from src.tools.definitions.speak import VOICES
from src.tools.definitions.transcribe import MAX_AUDIO_BYTES


router = APIRouter()
PCM_SAMPLE_RATE = 16000
OUTPUT_CHUNK_BYTES = 32 * 1024
logger = logging.getLogger(__name__)


class StsSession:
    def __init__(self, engine: Any, websocket: WebSocket, principal: Principal) -> None:
        self.engine = engine
        self.websocket = websocket
        self.principal = principal
        self.sessionId = f"sts_{uuid.uuid4().hex}"
        self.audioBuffer = bytearray()
        self.turnTask: asyncio.Task[None] | None = None
        self.started = False
        self.mode = ExecutionMode.FAST
        self.voice = "default"
        self.language: str | None = None
        self.connected = True

    async def run(self) -> None:
        async for raw in self.websocket.iter_text():
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await self._error("INVALID_JSON", "Message must be valid JSON.")
                continue
            if not isinstance(message, dict) or not isinstance(message.get("type"), str):
                await self._error("INVALID_MESSAGE", "Message must contain a type.")
                continue
            messageType = message["type"]
            if messageType == "session.start":
                await self._start(message)
            elif not self.started:
                await self._error("SESSION_NOT_STARTED", "Send session.start before other messages.")
            elif messageType == "audio.input":
                await self._appendAudio(message)
            elif messageType == "audio.commit":
                await self._commit()
            elif messageType == "response.cancel":
                await self._cancelTurn()
            elif messageType == "session.end":
                break
            else:
                await self._error("UNKNOWN_MESSAGE", "Unsupported session message type.")

    async def close(self) -> None:
        await self._cancelTurn()
        self.audioBuffer.clear()

    async def _start(self, message: dict[str, Any]) -> None:
        if self.started:
            await self._error("SESSION_ALREADY_STARTED", "Session configuration is already set.")
            return
        config = message.get("config", {})
        if not isinstance(config, dict):
            await self._error("INVALID_CONFIG", "Session config must be an object.")
            return
        try:
            self.mode = ExecutionMode(config.get("mode", "fast"))
        except ValueError:
            await self._error("INVALID_MODE", "Mode must be fast, auto, or expert.")
            return
        voice = config.get("voice", "default")
        language = config.get("language")
        if not isinstance(voice, str) or voice not in VOICES or (
            language is not None
            and (not isinstance(language, str) or re.fullmatch(r"[A-Za-z]{2}", language) is None)
        ):
            await self._error("INVALID_CONFIG", "Voice or language configuration is invalid.")
            return
        self.voice = voice
        self.language = language
        self.started = True
        await self.websocket.send_json({"type": "session.ready", "sessionId": self.sessionId})

    async def _appendAudio(self, message: dict[str, Any]) -> None:
        encoded = message.get("audio")
        if not isinstance(encoded, str):
            await self._error("INVALID_AUDIO", "audio.input requires base64 PCM16 audio.")
            return
        try:
            chunk = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            await self._error("INVALID_AUDIO", "Audio must be valid base64.")
            return
        if not chunk or len(self.audioBuffer) + len(chunk) > MAX_AUDIO_BYTES:
            await self._error("AUDIO_LIMIT", "Audio buffer is empty or exceeds the 25 MB limit.")
            return
        self.audioBuffer.extend(chunk)

    async def _commit(self) -> None:
        if self.turnTask is not None and not self.turnTask.done():
            await self._error("TURN_IN_PROGRESS", "Cancel the current response before committing another turn.")
            return
        if not self.audioBuffer:
            await self._error("EMPTY_AUDIO", "No audio has been buffered.")
            return
        audio = bytes(self.audioBuffer)
        self.audioBuffer.clear()
        self.turnTask = asyncio.create_task(self._runTurn(audio))

    async def _runTurn(self, pcmBytes: bytes) -> None:
        try:
            wavData = self._pcmAsWav(pcmBytes)
            transcription = await self.engine.toolExecutor.executeAsync({
                "name": "transcribe",
                "arguments": {
                    "operation": "audio",
                    "mediaData": base64.b64encode(wavData).decode("ascii"),
                    "mimeType": "audio/wav",
                    "fileName": "input.wav",
                    "language": self.language,
                },
            })
            if not isinstance(transcription, dict) or not transcription.get("success"):
                await self._error(
                    transcription.get("errorCode", "TRANSCRIPTION_FAILED") if isinstance(transcription, dict) else "TRANSCRIPTION_FAILED",
                    transcription.get("error", "Transcription failed.") if isinstance(transcription, dict) else "Transcription failed.",
                )
                return
            text = transcription.get("text", "").strip()
            await self.websocket.send_json({"type": "transcript.final", "text": text})
            if not text:
                await self.websocket.send_json({"type": "response.done"})
                return
            await self.websocket.send_json({"type": "agent.thinking"})
            response = await self.engine.run(
                prompt=text,
                sessionId=self.sessionId,
                principal=self.principal,
                mode=self.mode,
            )
            responseText = "".join(
                block.text or "" for block in response.content if block.type == "text"
            ).strip()
            if not responseText:
                await self._error("EMPTY_RESPONSE", "The agent did not return text to speak.")
                return
            speech = await self.engine.toolExecutor.executeAsync({
                "name": "speak",
                "arguments": {"operation": "text", "text": responseText, "voice": self.voice, "format": "pcm"},
            })
            if not isinstance(speech, dict) or not speech.get("success"):
                await self._error(
                    speech.get("errorCode", "SPEECH_FAILED") if isinstance(speech, dict) else "SPEECH_FAILED",
                    speech.get("error", "Speech generation failed.") if isinstance(speech, dict) else "Speech generation failed.",
                )
                return
            output = base64.b64decode(speech["mediaData"], validate=True)
            for index, offset in enumerate(range(0, len(output), OUTPUT_CHUNK_BYTES)):
                await self.websocket.send_json({
                    "type": "audio.output",
                    "audio": base64.b64encode(output[offset:offset + OUTPUT_CHUNK_BYTES]).decode("ascii"),
                    "mimeType": "audio/pcm",
                    "chunkIndex": index,
                    "last": offset + OUTPUT_CHUNK_BYTES >= len(output),
                })
            await self.websocket.send_json({"type": "response.done"})
        except asyncio.CancelledError:
            if self.connected:
                await self.websocket.send_json({"type": "response.done", "cancelled": True})
            raise
        except (binascii.Error, KeyError, TypeError, ValueError):
            await self._error("INVALID_AUDIO_RESULT", "An audio stage returned invalid data.")
        except Exception:
            logger.exception("Local STS pipeline failed for session %s", self.sessionId)
            await self._error("PIPELINE_FAILED", "The local speech pipeline failed.")

    async def _cancelTurn(self) -> None:
        task = self.turnTask
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Failed while cancelling STS turn for session %s", self.sessionId)
        self.turnTask = None
        self.audioBuffer.clear()

    async def _error(self, code: str, message: str) -> None:
        if self.connected:
            await self.websocket.send_json({"type": "error", "code": code, "message": message})

    @staticmethod
    def _pcmAsWav(pcmBytes: bytes) -> bytes:
        if len(pcmBytes) % 2:
            raise ValueError("PCM16 audio must contain whole samples.")
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(PCM_SAMPLE_RATE)
            wav.writeframes(pcmBytes)
        return output.getvalue()


@router.websocket("/v1/audio/sts")
async def sts_session(websocket: WebSocket) -> None:
    principal = getattr(websocket.state, "principal", None)
    if not isinstance(principal, Principal):
        await websocket.close(code=1008, reason="unauthenticated")
        return
    engine = getattr(websocket.app.state, "engine", None)
    if engine is None or not hasattr(engine, "toolExecutor"):
        await websocket.close(code=1011, reason="engine unavailable")
        return
    await websocket.accept()
    session = StsSession(engine, websocket, principal)
    try:
        await session.run()
    except WebSocketDisconnect:
        session.connected = False
    finally:
        await session.close()
