"""Audio metadata tools."""

import json
import math
import os
import shutil
import subprocess
from typing import Any
import uuid

from orchestrator.computer.workspace import SandboxPathError, safePath, workspaceRelativePath
from orchestrator.tools.actions import action_handler


def _failure(path: str, error: str, errorCode: str) -> dict[str, Any]:
    return {
        "success": False,
        "path": path,
        "durationSeconds": None,
        "sizeBytes": None,
        "formatName": None,
        "bitRate": None,
        "audioStreams": [],
        "error": error,
        "errorCode": errorCode,
    }


def _optionalInt(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


@action_handler("A2A7K4", "Inspecting audio metadata")
def audio(
    operation: str,
    path: str,
    output_path: str = "",
    start_seconds: float = 0,
    duration_seconds: float = 0,
    output_format: str = "",
) -> dict[str, Any]:
    """Return compact audio metadata using ffprobe when available."""
    if operation == "trim":
        return _trim(path, output_path, start_seconds, duration_seconds)
    if operation == "convert":
        return _convert(path, output_path, output_format)
    if operation != "probe":
        return {"success": False, "operation": operation, "path": path, "error": "Unsupported audio operation", "errorCode": "INVALID_OPERATION"}
    if not isinstance(path, str) or not path.strip():
        return _failure(str(path), "A file path is required", "INVALID_PATH")
    try:
        source = safePath(path, "read")
    except SandboxPathError as exc:
        return _failure(path, str(exc), "PATH_NOT_ALLOWED")
    if not source.is_file():
        return _failure(path, "Audio file was not found", "NOT_FOUND")

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return _failure(path, "ffprobe is not installed or is not on PATH", "FFPROBE_MISSING")

    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        if result.returncode != 0:
            return _failure(path, "ffprobe could not read the audio file", "FFPROBE_ERROR")
        data = json.loads(result.stdout)
        formatData = data.get("format", {})
        audioStreams = [
            {
                "codec": stream.get("codec_name"),
                "sampleRate": _optionalInt(stream.get("sample_rate")),
                "channels": _optionalInt(stream.get("channels")),
                "channelLayout": stream.get("channel_layout"),
                "bitRate": _optionalInt(stream.get("bit_rate")),
            }
            for stream in data.get("streams", [])
            if stream.get("codec_type") == "audio"
        ]
        try:
            durationSeconds = float(formatData["duration"]) if formatData.get("duration") is not None else None
        except (TypeError, ValueError, OverflowError):
            durationSeconds = None
        return {
            "success": True,
            "path": workspaceRelativePath(source),
            "durationSeconds": durationSeconds,
            "sizeBytes": _optionalInt(formatData.get("size")),
            "formatName": formatData.get("format_name"),
            "bitRate": _optionalInt(formatData.get("bit_rate")),
            "audioStreams": audioStreams,
            "error": None,
            "errorCode": None,
        }
    except subprocess.TimeoutExpired:
        return _failure(path, "Audio metadata probe timed out", "FFPROBE_TIMEOUT")
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        return _failure(path, "Audio metadata could not be decoded", "INVALID_METADATA")


@action_handler("A4R8D2", "Trimming an audio file")
def _trim(path: str, output_path: str, start_seconds: float, duration_seconds: float) -> dict[str, Any]:
    if not _validDuration(start_seconds) or not _validDuration(duration_seconds) or duration_seconds <= 0:
        return _operationFailure("trim", path, output_path, "Start and duration must be finite; duration must be positive", "INVALID_DURATION")
    if start_seconds > 86_400 or duration_seconds > 600:
        return _operationFailure("trim", path, output_path, "Trim range exceeds supported limits", "INVALID_DURATION")
    return _runFfmpeg(
        "trim", path, output_path,
        ["-ss", str(start_seconds), "-i", "{input}", "-t", str(duration_seconds), "-vn", "{output}"],
    )


@action_handler("A1C6V9", "Converting an audio file")
def _convert(path: str, output_path: str, output_format: str) -> dict[str, Any]:
    formats = {"wav", "mp3", "flac", "ogg", "m4a", "aac"}
    if not isinstance(output_format, str) or output_format not in formats or not isinstance(output_path, str) or not output_path.casefold().endswith(f".{output_format}"):
        return _operationFailure("convert", path, output_path, "Choose a supported audio format and matching output extension", "INVALID_FORMAT")
    return _runFfmpeg("convert", path, output_path, ["-i", "{input}", "-vn", "{output}"])


def _validDuration(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _operationFailure(operation: str, path: str, output_path: str, error: str, errorCode: str) -> dict[str, Any]:
    return {
        "success": False, "operation": operation,
        "path": path, "output": output_path, "error": error, "errorCode": errorCode,
    }


def _runFfmpeg(operation: str, path: str, output_path: str, arguments: list[str]) -> dict[str, Any]:
    failure = {
        "success": False, "operation": operation, "path": path, "output": output_path,
        "error": None, "errorCode": None,
    }
    try:
        source = safePath(path, "read")
        destination = safePath(output_path, "write")
    except SandboxPathError as exc:
        failure.update(error=str(exc), errorCode="PATH_NOT_ALLOWED")
        return failure
    if not source.is_file():
        failure.update(error="Audio file was not found", errorCode="NOT_FOUND")
        return failure
    if destination.exists():
        failure.update(error="Output file already exists", errorCode="OUTPUT_EXISTS")
        return failure
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        failure.update(error="ffmpeg is not installed or is not on PATH", errorCode="FFMPEG_MISSING")
        return failure

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        failure.update(error="Output directory could not be created", errorCode="WRITE_ERROR")
        return failure
    staging = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}{destination.suffix}")
    command = [ffmpeg, "-nostdin", "-v", "error", "-n"]
    for argument in arguments:
        if argument == "{input}":
            command.append(str(source))
        elif argument == "{output}":
            command.append(str(staging))
        else:
            command.append(argument)
    try:
        result = subprocess.run(command, capture_output=True, check=False, timeout=120)
        if result.returncode != 0:
            staging.unlink(missing_ok=True)
            failure.update(error="ffmpeg could not process the audio file", errorCode="FFMPEG_ERROR")
            return failure
        if not staging.is_file() or staging.stat().st_size == 0:
            staging.unlink(missing_ok=True)
            failure.update(error="ffmpeg produced no output file", errorCode="FFMPEG_ERROR")
            return failure
        if staging.stat().st_size > 20 * 1024 * 1024:
            staging.unlink(missing_ok=True)
            failure.update(error="Generated audio exceeds the inline media limit", errorCode="OUTPUT_TOO_LARGE")
            return failure
        try:
            os.link(staging, destination)
        except FileExistsError:
            staging.unlink(missing_ok=True)
            failure.update(error="Output file already exists", errorCode="OUTPUT_EXISTS")
            return failure
        staging.unlink(missing_ok=True)
        return {
            "success": True, "path": workspaceRelativePath(source),
            "output": workspaceRelativePath(destination), "error": None, "errorCode": None,
        }
    except subprocess.TimeoutExpired:
        staging.unlink(missing_ok=True)
        failure.update(error="Audio processing timed out", errorCode="FFMPEG_TIMEOUT")
        return failure
    except OSError:
        staging.unlink(missing_ok=True)
        failure.update(error="Audio processing failed", errorCode="FFMPEG_ERROR")
        return failure


_PROBE_ACTION_FACTORY = audio.__forge_action_factory__


def _action_factory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = arguments.get("operation")
    handlers = {
        "probe": _PROBE_ACTION_FACTORY,
        "trim": _trim.__forge_action_factory__,
        "convert": _convert.__forge_action_factory__,
    }
    factory = handlers.get(operation)
    if factory is None:
        raise ValueError(f"Unsupported audio operation: {operation}")
    return factory(tool_name, arguments)


setattr(audio, "__forge_action_factory__", _action_factory)


TOOLS = [{
    "type": "function",
    "function": {
        "name": "audio",
        "description": (
            "Inspect an audio file and return duration, format, size, bitrate, and per-audio-stream "
            "codec, sample rate, and channel information. Use when asked about an audio file's "
            "properties or before deciding whether it can be transcoded or transcribed. Requires ffprobe."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["probe", "trim", "convert"]},
                "path": {"type": "string", "description": "Path to the audio file"},
                "output_path": {"type": "string"},
                "start_seconds": {"type": "number", "minimum": 0, "maximum": 86400},
                "duration_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 600},
                "output_format": {"type": "string", "enum": ["wav", "mp3", "flac", "ogg", "m4a", "aac"]},
            },
            "required": ["operation", "path"],
            "allOf": [
                {"if": {"properties": {"operation": {"const": "trim"}}}, "then": {"required": ["output_path", "start_seconds", "duration_seconds"]}},
                {"if": {"properties": {"operation": {"const": "convert"}}}, "then": {"required": ["output_path", "output_format"]}},
            ],
            "additionalProperties": False,
        },
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "path": {"type": "string"},
            "durationSeconds": {"type": ["number", "null"]},
            "sizeBytes": {"type": ["integer", "null"]},
            "formatName": {"type": ["string", "null"]},
            "bitRate": {"type": ["integer", "null"]},
            "audioStreams": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "codec": {"type": ["string", "null"]},
                        "sampleRate": {"type": ["integer", "null"]},
                        "channels": {"type": ["integer", "null"]},
                        "channelLayout": {"type": ["string", "null"]},
                        "bitRate": {"type": ["integer", "null"]},
                    },
                    "required": ["codec", "sampleRate", "channels", "channelLayout", "bitRate"],
                    "additionalProperties": False,
                },
            },
            "error": {"type": ["string", "null"]},
            "errorCode": {"type": ["string", "null"]},
            "output": {"type": ["string", "null"]},
            "operation": {"type": ["string", "null"]},
        },
        "required": ["success", "error", "errorCode"],
        "additionalProperties": True,
    },
}]
HANDLERS = {"audio": audio}
