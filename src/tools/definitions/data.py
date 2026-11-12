"""Enterprise data analysis and reporting tools."""

import csv
import html
import io
import json
import sqlite3
from pathlib import Path
from typing import Any

from src.sandbox.pathPolicy import SandboxPathError, safePath as _safePath, workspaceRelativePath as _relativePath
from src.tools.actions import action_handler


def _failure(error: str, errorCode: str, **fields: Any) -> dict[str, Any]:
    return {"success": False, **fields, "error": error, "errorCode": errorCode}


def _records(frame, limit: int = 1000) -> list[dict[str, Any]]:
    safeFrame = frame.head(limit).astype(object).where(frame.head(limit).notna(), None)
    return json.loads(safeFrame.to_json(orient="records", date_format="iso"))


def _sanitizeCsvCell(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@action_handler("A6P3N8", "Analyzing a dataset", "data")
def _table(operation: str, path: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run bounded, read-only dataframe operations on an approved CSV dataset."""
    try:
        source = _safePath(path)
    except SandboxPathError as exc:
        return _failure(str(exc), "PATH_NOT_ALLOWED", path=str(path), operation=operation, result=None)
    if not source.is_file():
        return _failure("Dataset was not found", "NOT_FOUND", path=str(path), operation=operation, result=None)
    allowed = {"profile", "head", "describe", "groupby", "filter", "shape", "columns"}
    if operation not in allowed:
        return _failure("Unsupported pandas operation", "INVALID_OPERATION", path=_relativePath(source), operation=operation, result=None)

    options = options or {}
    try:
        import pandas as pd
        frame = pd.read_csv(source)
        if operation == "profile":
            result = {
                "rows": len(frame), "columns": len(frame.columns), "columnNames": frame.columns.tolist(),
                "dtypes": {key: str(value) for key, value in frame.dtypes.items()},
                "missing": {key: int(value) for key, value in frame.isna().sum().items()},
                "duplicateRows": int(frame.duplicated().sum()),
            }
        elif operation == "head":
            rows = max(1, min(int(options.get("rows", 5)), 100))
            result = _records(frame, rows)
        elif operation == "describe":
            result = json.loads(frame.describe(include="all").to_json())
        elif operation == "shape":
            result = {"rows": frame.shape[0], "columns": frame.shape[1]}
        elif operation == "columns":
            result = frame.columns.tolist()
        elif operation == "filter":
            column = options.get("column")
            if column not in frame.columns:
                return _failure(f"Unknown column: {column}", "UNKNOWN_COLUMN", path=_relativePath(source), operation=operation, result=None)
            if "equals" in options:
                frame = frame.loc[frame[column].astype(str) == str(options["equals"])]
            limit = max(1, min(int(options.get("limit", 100)), 1000))
            result = _records(frame, limit)
        else:
            column = options.get("column")
            aggregate = options.get("aggregate", "count")
            valueColumn = options.get("value_column")
            if column not in frame.columns:
                return _failure(f"Unknown grouping column: {column}", "UNKNOWN_COLUMN", path=_relativePath(source), operation=operation, result=None)
            if aggregate not in {"count", "sum", "mean", "min", "max"}:
                return _failure("Unsupported aggregate", "INVALID_AGGREGATE", path=_relativePath(source), operation=operation, result=None)
            if valueColumn is not None and valueColumn not in frame.columns:
                return _failure(f"Unknown value column: {valueColumn}", "UNKNOWN_COLUMN", path=_relativePath(source), operation=operation, result=None)
            if aggregate != "count" and valueColumn is None:
                return _failure("value_column is required for this aggregate", "MISSING_VALUE_COLUMN", path=_relativePath(source), operation=operation, result=None)
            grouped = frame.groupby(column, dropna=False)
            if aggregate == "count":
                aggregated = grouped[valueColumn].count() if valueColumn else grouped.size()
                result = _records(aggregated.rename("count").reset_index())
            else:
                aggregated = getattr(grouped[valueColumn], aggregate)()
                result = _records(aggregated.rename(aggregate).reset_index())
        return {"success": True, "path": _relativePath(source), "operation": operation, "result": result, "error": None, "errorCode": None}
    except ImportError:
        return _failure("pandas is not installed", "DEPENDENCY_MISSING", path=_relativePath(source), operation=operation, result=None)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _failure("Dataset could not be read or processed", "DATA_ERROR", path=_relativePath(source), operation=operation, result=None)
    except (TypeError, ValueError, OverflowError) as exc:
        return _failure(str(exc)[:300], "INVALID_OPTIONS", path=_relativePath(source), operation=operation, result=None)


@action_handler("A8Q1R5", "Running a read-only SQL query", "data")
def _sql(connection: str, query: str, parameters: list[Any] | None = None) -> dict[str, Any]:
    output = {"connection": str(connection), "rowCount": 0, "rows": []}
    if not isinstance(query, str) or not query.strip():
        return _failure("A SQL query is required", "INVALID_QUERY", **output)
    if not query.lstrip().upper().startswith(("SELECT", "WITH", "PRAGMA")):
        return _failure("Only read-only SELECT, WITH, and query-only PRAGMA statements are supported", "READ_ONLY_QUERY_REQUIRED", **output)
    if not isinstance(connection, str) or not connection.startswith("sqlite:"):
        return _failure("Only SQLite database paths are supported", "UNSUPPORTED_CONNECTION", **output)
    try:
        database = _safePath(connection.removeprefix("sqlite:"))
    except SandboxPathError as exc:
        return _failure(str(exc), "PATH_NOT_ALLOWED", **output)
    if not database.is_file():
        return _failure("Database file was not found", "NOT_FOUND", **output)

    deniedActions = {
        getattr(sqlite3, name)
        for name in (
            "SQLITE_INSERT", "SQLITE_UPDATE", "SQLITE_DELETE", "SQLITE_CREATE_INDEX", "SQLITE_CREATE_TABLE",
            "SQLITE_CREATE_TRIGGER", "SQLITE_CREATE_VIEW", "SQLITE_DROP_INDEX", "SQLITE_DROP_TABLE",
            "SQLITE_DROP_TRIGGER", "SQLITE_DROP_VIEW", "SQLITE_ALTER_TABLE", "SQLITE_ATTACH", "SQLITE_DETACH",
            "SQLITE_REINDEX", "SQLITE_ANALYZE",
        )
        if hasattr(sqlite3, name)
    }

    def authorize(action, arg1, arg2, databaseName, triggerName):
        if action in deniedActions:
            return sqlite3.SQLITE_DENY
        if action == getattr(sqlite3, "SQLITE_PRAGMA", -1) and arg2 is not None:
            return sqlite3.SQLITE_DENY
        if action == getattr(sqlite3, "SQLITE_FUNCTION", -1) and str(arg2 or arg1).casefold() in {"load_extension", "readfile", "writefile"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    try:
        databaseUri = f"{database.as_uri()}?mode=ro"
        with sqlite3.connect(databaseUri, uri=True) as client:
            client.row_factory = sqlite3.Row
            client.set_authorizer(authorize)
            rows = [dict(row) for row in client.execute(query, parameters or []).fetchmany(1000)]
        output.update({"success": True, "connection": _relativePath(database), "rowCount": len(rows), "rows": rows, "error": None, "errorCode": None})
        return output
    except (sqlite3.Error, TypeError, ValueError):
        return _failure("The read-only query could not be executed", "QUERY_ERROR", **output)


@action_handler("A3D9W2", "Profiling a dataset", "data")
def _profile(path: str) -> dict[str, Any]:
    result = _table("profile", path)
    return {"success": result["success"], "path": result["path"], "profile": result.get("result"), "error": result["error"], "errorCode": result["errorCode"]}


@action_handler("A5J4H7", "Joining datasets", "data")
def _join(left_path: str, right_path: str, left_key: str, right_key: str | None = None, join_type: str = "inner") -> dict[str, Any]:
    if join_type not in {"inner", "left", "right", "outer"}:
        return _failure("Unsupported join type", "INVALID_JOIN_TYPE", rowCount=0, columns=[], rows=[])
    try:
        left = _safePath(left_path)
        right = _safePath(right_path)
    except SandboxPathError as exc:
        return _failure(str(exc), "PATH_NOT_ALLOWED", rowCount=0, columns=[], rows=[])
    if not left.is_file() or not right.is_file():
        return _failure("One or both datasets were not found", "NOT_FOUND", rowCount=0, columns=[], rows=[])
    try:
        import pandas as pd

        leftFrame = pd.read_csv(left)
        rightFrame = pd.read_csv(right)
        rightKey = right_key or left_key
        if left_key not in leftFrame.columns or rightKey not in rightFrame.columns:
            return _failure("Join key was not found in both datasets", "UNKNOWN_COLUMN", rowCount=0, columns=[], rows=[])
        output = leftFrame.merge(rightFrame, left_on=left_key, right_on=rightKey, how=join_type)
        return {"success": True, "rowCount": len(output), "columns": output.columns.tolist(), "rows": _records(output), "error": None, "errorCode": None}
    except ImportError:
        return _failure("pandas is not installed", "DEPENDENCY_MISSING", rowCount=0, columns=[], rows=[])
    except (OSError, UnicodeError, ValueError, TypeError):
        return _failure("Datasets could not be joined", "JOIN_ERROR", rowCount=0, columns=[], rows=[])


@action_handler("A1V6C3", "Compiling a report", "data")
def _report(title: str, sections: list[dict[str, str]], format: str = "markdown", output_path: str | None = None) -> dict[str, Any]:
    base = {"format": format, "content": None, "path": None, "bytes": 0}
    if not isinstance(title, str) or not isinstance(sections, list) or any(not isinstance(item, dict) or not isinstance(item.get("title"), str) or not isinstance(item.get("content"), str) for item in sections):
        return _failure("Title and sections have an invalid structure", "INVALID_REPORT", **base)
    if format not in {"markdown", "html", "json", "csv"}:
        return _failure("Unsupported report format", "INVALID_FORMAT", **base)
    if format == "markdown":
        body = f"# {title}\n\n" + "\n\n".join(f"## {item['title']}\n\n{item['content']}" for item in sections)
    elif format == "html":
        body = f"<!doctype html><html><body><h1>{html.escape(title)}</h1>" + "".join(f"<section><h2>{html.escape(item['title'])}</h2><p>{html.escape(item['content'])}</p></section>" for item in sections) + "</body></html>"
    elif format == "json":
        body = json.dumps({"title": title, "sections": sections}, ensure_ascii=False, indent=2)
    else:
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["title", "section", "content"])
        writer.writerows([_sanitizeCsvCell(title), _sanitizeCsvCell(item["title"]), _sanitizeCsvCell(item["content"])] for item in sections)
        body = output.getvalue()
    if output_path:
        try:
            destination = _safePath(output_path, "write")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(body, encoding="utf-8", newline="")
            base.update({"success": True, "content": None, "path": _relativePath(destination), "bytes": len(body.encode("utf-8")), "error": None, "errorCode": None})
            return base
        except SandboxPathError as exc:
            return _failure(str(exc), "PATH_NOT_ALLOWED", **base)
        except OSError:
            return _failure("Report could not be written", "WRITE_ERROR", **base)
    base.update({"success": True, "content": body, "error": None, "errorCode": None})
    return base


@action_handler("A7B2L9", "Creating a chart", "data")
def _chart(path: str, chart_type: str, x_column: str, y_column: str | None = None, output_path: str = "outputs/chart.png") -> dict[str, Any]:
    try:
        source = _safePath(path)
        destination = _safePath(output_path, "write")
    except SandboxPathError as exc:
        return _failure(str(exc), "PATH_NOT_ALLOWED", path=str(output_path), chartType=chart_type)
    if not source.is_file():
        return _failure("Dataset was not found", "NOT_FOUND", path=str(path), chartType=chart_type)
    if chart_type not in {"line", "bar", "histogram", "scatter"}:
        return _failure("Unsupported chart type", "INVALID_CHART_TYPE", path=str(output_path), chartType=chart_type)
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        import pandas as pd

        frame = pd.read_csv(source)
        if x_column not in frame.columns or (y_column is not None and y_column not in frame.columns):
            return _failure("Chart column was not found", "UNKNOWN_COLUMN", path=str(output_path), chartType=chart_type)
        if chart_type in {"line", "bar", "scatter"} and not y_column:
            return _failure("y_column is required for this chart type", "MISSING_COLUMN", path=str(output_path), chartType=chart_type)
        destination.parent.mkdir(parents=True, exist_ok=True)
        figure, axis = plt.subplots()
        if chart_type == "line":
            frame.plot(x=x_column, y=y_column, kind="line", ax=axis)
        elif chart_type == "bar":
            frame.groupby(x_column)[y_column].sum().plot(kind="bar", ax=axis)
        elif chart_type == "histogram":
            frame[x_column].plot(kind="hist", ax=axis)
        else:
            frame.plot(kind="scatter", x=x_column, y=y_column, ax=axis)
        figure.tight_layout()
        figure.savefig(destination)
        plt.close(figure)
        return {"success": True, "path": _relativePath(destination), "chartType": chart_type, "error": None, "errorCode": None}
    except ImportError:
        return _failure("pandas and matplotlib are required for chart creation", "DEPENDENCY_MISSING", path=str(output_path), chartType=chart_type)
    except (OSError, ValueError, TypeError):
        return _failure("Chart could not be created", "CHART_ERROR", path=str(output_path), chartType=chart_type)


_OPERATIONS = {
    "table": _table,
    "sql": _sql,
    "profile": _profile,
    "join": _join,
    "report": _report,
    "chart": _chart,
}

_REQUIRED_ARGUMENTS = {
    "table": ("path", "options"),
    "sql": ("connection", "query"),
    "profile": ("path",),
    "join": ("left_path", "right_path", "left_key"),
    "report": ("title", "sections"),
    "chart": ("path", "chart_type", "x_column"),
}


@action_handler("A6P3N8", "Analyzing data", "data")
def data(operation: str, **parameters: Any) -> dict[str, Any]:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return _failure("Unsupported data operation", "INVALID_OPERATION", operation=operation)
    missing = [name for name in _REQUIRED_ARGUMENTS[operation] if name not in parameters]
    if missing:
        return _failure(
            f"Missing required arguments for {operation}: {', '.join(missing)}",
            "INVALID_ARGUMENTS",
            operation=operation,
        )
    if operation == "table":
        options = parameters.get("options")
        if not isinstance(options, dict) or not isinstance(options.get("operation"), str):
            return _failure("Table options must include an operation", "INVALID_ARGUMENTS", operation=operation)
        return handler(
            operation=options["operation"],
            path=parameters["path"],
            options=options,
        )
    return handler(**parameters)


def _action_factory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = arguments.get("operation")
    handler = _OPERATIONS.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported data operation: {operation}")
    factory = getattr(handler, "__forge_action_factory__")
    return factory(tool_name, arguments)


setattr(data, "__forge_action_factory__", _action_factory)

_PARAMETER_PROPERTIES = {
    "operation": {"type": "string", "enum": list(_OPERATIONS)},
    "path": {"type": "string", "description": "CSV path relative to the configured data directory"},
    "options": {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["profile", "head", "describe", "groupby", "filter", "shape", "columns"]},
            "rows": {"type": "integer", "minimum": 1, "maximum": 100},
            "column": {"type": "string"},
            "equals": {},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            "aggregate": {"type": "string", "enum": ["count", "sum", "mean", "min", "max"]},
            "value_column": {"type": "string"},
        },
        "required": ["operation"],
        "additionalProperties": False,
    },
    "connection": {"type": "string", "description": "SQLite path such as 'sqlite:analytics.db'"},
    "query": {"type": "string"},
    "parameters": {"type": "array", "items": {}},
    "left_path": {"type": "string"},
    "right_path": {"type": "string"},
    "left_key": {"type": "string"},
    "right_key": {"type": "string"},
    "join_type": {"type": "string", "enum": ["inner", "left", "right", "outer"], "default": "inner"},
    "title": {"type": "string"},
    "sections": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
            "required": ["title", "content"],
            "additionalProperties": False,
        },
    },
    "format": {"type": "string", "enum": ["markdown", "html", "json", "csv"], "default": "markdown"},
    "output_path": {"type": "string"},
    "chart_type": {"type": "string", "enum": ["line", "bar", "histogram", "scatter"]},
    "x_column": {"type": "string"},
    "y_column": {"type": "string"},
}

_OPERATION_REQUIREMENTS = [
    {"if": {"properties": {"operation": {"const": operation}}}, "then": {"required": list(required)}}
    for operation, required in _REQUIRED_ARGUMENTS.items()
]

TOOLS = [{
    "type": "function",
    "function": {
        "name": "data",
        "description": (
            "Analyze CSV and SQLite datasets: inspect tables, profile data, join datasets, "
            "run read-only SQL, compile reports, and create charts. Choose exactly one operation. "
            "Use for dataset files and data questions, not image, audio, or video files."
        ),
        "parameters": {
            "type": "object",
            "properties": _PARAMETER_PROPERTIES,
            "required": ["operation"],
            "allOf": _OPERATION_REQUIREMENTS,
            "additionalProperties": False,
        },
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "error": {"type": ["string", "null"]},
            "errorCode": {"type": ["string", "null"]},
        },
        "required": ["success", "error", "errorCode"],
        "additionalProperties": True,
    },
}]
HANDLERS = {"data": data}
