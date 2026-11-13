"""Video metadata tools."""

import json
import math
import shutil
import subprocess
from typing import Any

from orchestrator.computer.workspace import SandboxPathError, safePath, workspaceRelativePath
from orchestrator.tools.actions import action_handler


def _failure(error: str, errorCode: str, **fields: Any) -> dict[str, Any]:
    return {"success": False, **fields, "error": error, "errorCode": errorCode}


@action_handler("A4X6B2", "Inspecting video metadata")
def probe(path: str) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
    except SandboxPathError as exc:
        return _failure(str(exc), "PATH_NOT_ALLOWED", path=path, durationSeconds=None, sizeBytes=None, formatName=None, bitRate=None, videoStreams=[])
    if not source.is_file():
        return _failure("Video file was not found", "NOT_FOUND", path=path, durationSeconds=None, sizeBytes=None, formatName=None, bitRate=None, videoStreams=[])

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return _failure("ffprobe is not installed or is not on PATH", "FFPROBE_MISSING", path=workspaceRelativePath(source), durationSeconds=None, sizeBytes=None, formatName=None, bitRate=None, videoStreams=[])

    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)],
            capture_output=True, text=True, check=False, timeout=20,
        )
        if result.returncode != 0:
            return _failure("ffprobe could not read the video file", "FFPROBE_ERROR", path=workspaceRelativePath(source), durationSeconds=None, sizeBytes=None, formatName=None, bitRate=None, videoStreams=[])
        data = json.loads(result.stdout)
        formatData = data.get("format", {})
        videoStreams = [{
            "codec": stream.get("codec_name"),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "frameRate": stream.get("r_frame_rate"),
            "bitRate": _optionalInt(stream.get("bit_rate")),
        } for stream in data.get("streams", []) if stream.get("codec_type") == "video"]
        return {
            "success": True, "path": workspaceRelativePath(source),
            "durationSeconds": _optionalFloat(formatData.get("duration")),
            "sizeBytes": _optionalInt(formatData.get("size")),
            "formatName": formatData.get("format_name"),
            "bitRate": _optionalInt(formatData.get("bit_rate")),
            "videoStreams": videoStreams, "error": None, "errorCode": None,
        }
    except subprocess.TimeoutExpired:
        return _failure("Video metadata probe timed out", "FFPROBE_TIMEOUT", path=workspaceRelativePath(source), durationSeconds=None, sizeBytes=None, formatName=None, bitRate=None, videoStreams=[])
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        return _failure("Video metadata could not be decoded", "INVALID_METADATA", path=workspaceRelativePath(source), durationSeconds=None, sizeBytes=None, formatName=None, bitRate=None, videoStreams=[])


def _optionalInt(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _optionalFloat(value: Any) -> float | None:
    try:
        parsed = float(value) if value is not None else None
        return parsed if parsed is None or math.isfinite(parsed) else None
    except (TypeError, ValueError, OverflowError):
        return None


@action_handler("A9A1M7", "Sampling video frames")
def sample(path: str, timestamps: list[float], output_directory: str) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
        destination = safePath(output_directory, "write", isDirectory=True)
    except SandboxPathError as exc:
        return _failure(str(exc), "PATH_NOT_ALLOWED", frames=[])
    ffmpeg = shutil.which("ffmpeg")
    if not source.is_file():
        return _failure("Video file was not found", "NOT_FOUND", frames=[])
    if ffmpeg is None:
        return _failure("ffmpeg is not installed or is not on PATH", "FFMPEG_MISSING", frames=[])
    if not isinstance(timestamps, list) or not timestamps or len(timestamps) > 100:
        return _failure("Provide between 1 and 100 frame timestamps", "INVALID_TIMESTAMPS", frames=[])
    destination.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, timestamp in enumerate(timestamps):
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp < 0:
            return _failure("Frame timestamps must be finite non-negative numbers", "INVALID_TIMESTAMP", frames=frames)
        output = destination / f"frame_{index:06d}.jpg"
        try:
            subprocess.run([ffmpeg, "-v", "error", "-ss", str(timestamp), "-i", str(source), "-frames:v", "1", "-y", str(output)], capture_output=True, text=True, timeout=30, check=True)
            frames.append(workspaceRelativePath(output))
        except (OSError, subprocess.SubprocessError):
            return _failure("ffmpeg could not sample a requested frame", "FFMPEG_ERROR", frames=frames)
    return {"success": True, "path": workspaceRelativePath(source), "frames": frames, "error": None, "errorCode": None}


@action_handler("A2C8R5", "Extracting video keyframes")
def keyframe(path: str, output_directory: str, threshold: float = 0.3) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
        destination = safePath(output_directory, "write", isDirectory=True)
    except SandboxPathError as exc:
        return _failure(str(exc), "PATH_NOT_ALLOWED", keyframes=[], threshold=threshold)
    ffmpeg = shutil.which("ffmpeg")
    if not source.is_file():
        return _failure("Video file was not found", "NOT_FOUND", keyframes=[], threshold=threshold)
    if ffmpeg is None:
        return _failure("ffmpeg is not installed or is not on PATH", "FFMPEG_MISSING", keyframes=[], threshold=threshold)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        return _failure("threshold must be between 0 and 1", "INVALID_THRESHOLD", keyframes=[], threshold=threshold)
    destination.mkdir(parents=True, exist_ok=True)
    output_pattern = destination / "keyframe_%06d.jpg"
    filter_expression = f"select='gt(scene,{threshold})'"
    try:
        subprocess.run([ffmpeg, "-v", "error", "-i", str(source), "-vf", filter_expression, "-fps_mode", "vfr", "-y", str(output_pattern)], capture_output=True, text=True, timeout=120, check=True)
        frames = [workspaceRelativePath(frame) for frame in sorted(destination.glob("keyframe_*.jpg"))]
        return {"success": True, "path": workspaceRelativePath(source), "keyframes": frames, "threshold": threshold, "error": None, "errorCode": None}
    except (OSError, subprocess.SubprocessError):
        return _failure("ffmpeg could not extract keyframes", "FFMPEG_ERROR", keyframes=[], threshold=threshold)


_OPERATIONS = {"probe": probe, "sample": sample, "keyframe": keyframe}


def video(operation: str, **arguments: Any) -> dict[str, Any]:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return _failure("Unsupported video operation", "INVALID_OPERATION")
    return handler(**arguments)


def _action_factory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = arguments.get("operation")
    handler = _OPERATIONS.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported video operation: {operation}")
    factory = getattr(handler, "__forge_action_factory__")
    return factory(tool_name, arguments)


setattr(video, "__forge_action_factory__", _action_factory)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "video",
        "description": "Inspect video metadata or extract frames. Choose probe for file properties, sample for specified timestamps, or keyframe for scene changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "path": {"type": "string"},
                "timestamps": {"type": "array", "items": {"type": "number"}, "minItems": 1, "maxItems": 100},
                "output_directory": {"type": "string"},
                "threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.3},
            },
            "required": ["operation"],
            "allOf": [
                {"if": {"properties": {"operation": {"const": operation}}}, "then": {"required": required}}
                for operation, required in {
                    "probe": ["path"],
                    "sample": ["path", "timestamps", "output_directory"],
                    "keyframe": ["path", "output_directory"],
                }.items()
            ],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"video": video}
