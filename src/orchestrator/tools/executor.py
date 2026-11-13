"""Shared execution entry point for orchestrator-owned local tools."""

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

import jsonschema

from orchestrator.media import MediaConversionError, MediaConverter
from orchestrator.computer.manager import ComputerManager

@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def toDict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "code": self.code,
            "metadata": self.metadata,
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.toDict().get(key, default)


class ToolExecutor:
    def __init__(
        self,
        registry=None,
        mediaConverter: MediaConverter | None = None,
        toolDependencies: Mapping[str, Mapping[str, Any]] | None = None,
        computerManager: ComputerManager | None = None,
        auditLog=None,
    ) -> None:
        if registry is None:
            from orchestrator.tools.registry import create_default_registry

            registry = create_default_registry()
        self.registry = registry
        self.mediaConverter = mediaConverter or MediaConverter.from_environment()
        self.computerManager = computerManager or ComputerManager(audit_log=auditLog)
        if computerManager is not None and auditLog is not None:
            computerManager.audit_log = auditLog
        self.toolDependencies = {
            name: dict(dependencies)
            for name, dependencies in (toolDependencies or {}).items()
        }
        self.toolDependencies.setdefault("computer", {})["computerManager"] = self.computerManager

    async def close(self) -> None:
        await self.computerManager.close()

    async def closeComputerSession(
        self,
        run_id: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        session_id = self._computerSessionId({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "run_id": run_id,
        }) or run_id
        await self.computerManager.close_session(session_id)

    def execute(self, tool_call: Mapping[str, Any]) -> Any:
        name, arguments, validation_error = self._validated_call(tool_call)
        if validation_error:
            return validation_error
        return self.registry.execute(name, self._argumentsWithDependencies(name, arguments))

    async def executeAsync(self, tool_call: Mapping[str, Any], context: Mapping[str, Any] | None = None) -> Any:
        name, arguments, validation_error = self._validated_call(tool_call)
        if validation_error:
            return validation_error
        dependencies = self._argumentsWithDependencies(name, arguments)
        if name == "computer" and context is not None:
            session_id = self._computerSessionId(context)
            if session_id is not None:
                dependencies["computerSessionId"] = session_id
                dependencies["computerTenantId"] = context.get("tenant_id")
                dependencies["computerUserId"] = context.get("user_id")
                dependencies["computerRunId"] = context.get("run_id")
        result = self.registry.execute(name, dependencies)
        result = await result if inspect.isawaitable(result) else result
        return await self._normalizeMediaResult(result)

    def _argumentsWithDependencies(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {**arguments, **self.toolDependencies.get(name, {})}

    @staticmethod
    def _computerSessionId(context: Mapping[str, Any]) -> str | None:
        session_parts = [context.get(key) for key in ("tenant_id", "user_id", "run_id")]
        if not all(isinstance(part, str) and part for part in session_parts):
            return None
        return json.dumps(session_parts, separators=(",", ":"))

    async def _normalizeMediaResult(self, result: Any) -> Any:
        if isinstance(result, ToolResult):
            normalized = await self._normalizeMediaResult(result.toDict())
            return ToolResult(**normalized) if isinstance(normalized, dict) else normalized
        if not isinstance(result, dict):
            return result
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        mediaType = data.get("mediaType", data.get("type"))
        urlKeys = [
            key for key in ("url", "imageUrl", "fileUrl", "mediaUrl")
            if isinstance(data.get(key), str)
        ]
        if not urlKeys:
            path = data.get("outputPath", data.get("path"))
            if isinstance(path, str) and mediaType in {"image", "video", "audio", "file"}:
                try:
                    from orchestrator.computer.workspace import safePath

                    inline = self.mediaConverter.fromFile(safePath(path, mode="read"))
                except (MediaConversionError, ValueError, OSError):
                    return ToolResult(False, error="Media conversion failed", code="MEDIA_CONVERSION_FAILED").toDict()
                data.update({
                    "mediaData": inline.mediaData,
                    "mimeType": inline.mimeType,
                    "fileName": inline.fileName,
                    "fileSizeBytes": inline.fileSizeBytes,
                })
                data.pop("outputPath", None)
                data.pop("path", None)
            return result

        if urlKeys[0] == "url" and "mimeType" not in data and mediaType not in {"image", "video", "audio", "file"}:
            return result
        urlKey = urlKeys[0]
        try:
            inline = await self.mediaConverter.fromUrl(data[urlKey], data.get("fileName"))
        except MediaConversionError:
            return ToolResult(False, error="Media conversion failed", code="MEDIA_CONVERSION_FAILED").toDict()
        for key in urlKeys:
            data.pop(key, None)
        data.update({
            "mediaData": inline.mediaData,
            "mimeType": inline.mimeType,
            "fileName": inline.fileName,
            "fileSizeBytes": inline.fileSizeBytes,
        })
        return result

    async def normalizeMediaResult(self, result: Any) -> Any:
        return await self._normalizeMediaResult(result)

    def _validated_call(self, tool_call: Mapping[str, Any]) -> tuple[str, dict[str, Any], ToolResult | None]:
        function = tool_call.get("function", {})
        name = function.get("name", tool_call.get("name"))
        arguments = function.get("arguments", tool_call.get("arguments", {}))
        if not isinstance(name, str) or not name:
            return "", {}, ToolResult(False, error="Tool name is required", code="UNKNOWN_TOOL")
        definition = self.registry.get(name)
        if definition is None:
            return name, {}, ToolResult(False, error=f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return name, {}, ToolResult(False, error="Tool arguments must be valid JSON", code="INVALID_ARGUMENTS")
        if not isinstance(arguments, Mapping):
            return name, {}, ToolResult(False, error="Tool arguments must be a JSON object", code="INVALID_ARGUMENTS")
        function_definition = definition.get("function", definition)
        schema = function_definition.get("parameters") if isinstance(function_definition, Mapping) else None
        if not isinstance(schema, Mapping):
            return name, {}, ToolResult(False, error=f"Tool '{name}' has no argument schema", code="NO_SCHEMA")
        try:
            jsonschema.validate(instance=dict(arguments), schema=schema)
        except jsonschema.ValidationError as exc:
            errorPath = list(exc.absolute_path)
            schemaPath = list(exc.absolute_schema_path)
            return name, {}, ToolResult(
                False,
                error=f"Invalid arguments for '{name}': {exc.message}",
                code="INVALID_ARGUMENTS",
                metadata={"path": errorPath, "schemaPath": schemaPath},
            )
        except jsonschema.SchemaError as exc:
            return name, {}, ToolResult(False, error=f"Tool '{name}' has an invalid argument schema", code="INVALID_SCHEMA")
        return name, dict(arguments), None
