"""CSV spreadsheet tools."""

import csv
from typing import Any

from orchestrator.computer.workspace import SandboxPathError, safePath, workspaceRelativePath
from orchestrator.tools.actions import action_handler


DEFAULT_MAX_ROWS = 100
MAX_MAX_ROWS = 500
MAX_WRITE_ROWS = 500


def _errorResult(path: str, error: str, errorCode: str, *, write: bool = False) -> dict[str, Any]:
    if write:
        return {"success": False, "path": path, "rowCount": 0, "error": error, "errorCode": errorCode}
    return {
        "success": False, "path": path, "headers": [], "rows": [], "rowCount": 0,
        "error": error, "errorCode": errorCode,
    }


def _sanitizeCell(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@action_handler("A1G9V4", "Reading a CSV file", "data")
def read(path: str, delimiter: str = ",", maxRows: int = DEFAULT_MAX_ROWS) -> dict[str, Any]:
    try:
        source = safePath(path, "read")
    except SandboxPathError as exc:
        return _errorResult(path, str(exc), "PATH_NOT_ALLOWED")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        return _errorResult(path, "Delimiter must be exactly one character", "INVALID_DELIMITER")
    if isinstance(maxRows, bool) or not isinstance(maxRows, int) or maxRows < 1:
        return _errorResult(path, "maxRows must be a positive integer", "INVALID_LIMIT")
    if not source.is_file():
        return _errorResult(path, "CSV file was not found", "NOT_FOUND")
    maxRows = min(maxRows, MAX_MAX_ROWS)

    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            headers = reader.fieldnames or []
            rows = []
            for rowIndex, row in enumerate(reader):
                if rowIndex >= maxRows:
                    break
                rows.append(row)
        return {
            "success": True, "path": workspaceRelativePath(source),
            "headers": headers, "rows": rows, "rowCount": len(rows), "error": None, "errorCode": None,
        }
    except (OSError, UnicodeError, csv.Error) as exc:
        return _errorResult(path, "CSV file could not be read", "READ_ERROR")


@action_handler("A7K3Q8", "Writing a CSV file", "data")
def write(path: str, headers: list[str], rows: list[list[Any]], delimiter: str = ",") -> dict[str, Any]:
    try:
        destination = safePath(path, "write")
    except SandboxPathError as exc:
        return _errorResult(path, str(exc), "PATH_NOT_ALLOWED", write=True)
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        return _errorResult(path, "Delimiter must be exactly one character", "INVALID_DELIMITER", write=True)
    if not isinstance(headers, list) or not headers or not all(isinstance(header, str) for header in headers):
        return _errorResult(path, "Headers must be a non-empty list of strings", "INVALID_HEADERS", write=True)
    if not isinstance(rows, list) or len(rows) > MAX_WRITE_ROWS:
        return _errorResult(path, f"Rows must be a list with no more than {MAX_WRITE_ROWS} entries", "INVALID_ROWS", write=True)
    if any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
        return _errorResult(path, "Every row must contain one value per header", "INVALID_ROWS", write=True)

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=delimiter)
            writer.writerow([_sanitizeCell(header) for header in headers])
            writer.writerows([_sanitizeCell(value) for value in row] for row in rows)
        return {
            "success": True, "path": workspaceRelativePath(destination),
            "rowCount": len(rows), "error": None, "errorCode": None,
        }
    except (OSError, csv.Error):
        return _errorResult(path, "CSV file could not be written", "WRITE_ERROR", write=True)


@action_handler("A6I2N5", "Inspecting spreadsheet structure", "data")
def _info(path: str, delimiter: str = ",") -> dict[str, Any]:
    try:
        source = safePath(path, "read")
    except SandboxPathError as exc:
        return _errorResult(path, str(exc), "PATH_NOT_ALLOWED")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        return _errorResult(path, "Delimiter must be exactly one character", "INVALID_DELIMITER")
    if not source.is_file():
        return _errorResult(path, "CSV file was not found", "NOT_FOUND")
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            headers = next(reader, [])
            rowCount = sum(1 for _ in reader)
        return {
            "success": True, "path": workspaceRelativePath(source),
            "headers": headers, "rows": [], "rowCount": rowCount,
            "error": None, "errorCode": None,
        }
    except (OSError, UnicodeError, csv.Error):
        return _errorResult(path, "CSV structure could not be read", "READ_ERROR")


@action_handler("A1G9V4", "Reading or writing a spreadsheet", "data")
def sheet(
    operation: str,
    path: str,
    headers: list[str] | None = None,
    rows: list[list[Any]] | None = None,
    delimiter: str = ",",
    maxRows: int = DEFAULT_MAX_ROWS,
) -> dict[str, Any]:
    if operation == "read":
        return read(path, delimiter=delimiter, maxRows=maxRows)
    if operation == "write":
        if headers is None or rows is None:
            return _errorResult(path, "headers and rows are required for write", "INVALID_ARGUMENTS", write=True)
        return write(path, headers, rows, delimiter=delimiter)
    if operation == "info":
        return _info(path, delimiter=delimiter)
    return _errorResult(path, "operation must be read or write", "INVALID_OPERATION")


def _action_factory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = arguments.get("operation")
    handlers = {"read": read, "write": write, "info": _info}
    handler = handlers.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported spreadsheet operation: {operation}")
    return handler.__forge_action_factory__(tool_name, arguments)


setattr(sheet, "__forge_action_factory__", _action_factory)


TOOLS = [{
    "type": "function",
    "function": {
        "name": "sheet",
        "description": (
            "Read or write bounded CSV spreadsheets inside the configured data directory. Use "
            "operation='read' to inspect a file or operation='write' only when the user asks to "
            "create/export CSV data. Writes escape formula-leading cells."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["read", "write", "info"]},
                "path": {"type": "string"},
                "headers": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array"}},
                "delimiter": {"type": "string", "default": ","},
                "maxRows": {"type": "integer", "minimum": 1, "maximum": MAX_MAX_ROWS, "default": DEFAULT_MAX_ROWS},
            },
            "required": ["operation", "path"],
            "allOf": [{
                "if": {"properties": {"operation": {"const": "write"}}},
                "then": {"required": ["headers", "rows"]},
            }],
            "additionalProperties": False,
        },
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "path": {"type": "string"},
            "headers": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "items": {"type": "object"}},
            "rowCount": {"type": "integer"},
            "error": {"type": ["string", "null"]},
            "errorCode": {"type": ["string", "null"]},
        },
        "required": ["success", "path", "rowCount", "error", "errorCode"],
        "additionalProperties": False,
    },
}]
HANDLERS = {"sheet": sheet}
