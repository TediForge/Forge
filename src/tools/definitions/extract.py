"""Bounded local extraction of structured text formats."""

import csv
import io
import json
import xml.etree.ElementTree as ET
from typing import Any

import jsonschema

from src.tools.actions import action_handler


MAX_TEXT_CHARS = 100_000
MAX_SCHEMA_CHARS = 32_000
MAX_JSON_CANDIDATES = 100
MAX_CSV_ROWS = 500


@action_handler("A6E4X8", "Extracting structured JSON")
def _extractJson(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        return _failure("json", "Text must be non-empty", "INVALID_TEXT")
    if len(text) > MAX_TEXT_CHARS:
        return _failure("json", "Text exceeds the supported size", "TEXT_TOO_LARGE")
    if not isinstance(schema, dict):
        return _failure("json", "A bounded JSON Schema object is required", "INVALID_SCHEMA")
    try:
        if len(json.dumps(schema)) > MAX_SCHEMA_CHARS or _containsReference(schema):
            return _failure("json", "Schema is too large or contains unsupported references", "INVALID_SCHEMA")
    except (TypeError, ValueError, RecursionError):
        return _failure("json", "A bounded JSON Schema object is required", "INVALID_SCHEMA")

    decoder = json.JSONDecoder()
    candidateCount = 0
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        candidateCount += 1
        if candidateCount > MAX_JSON_CANDIDATES:
            return _failure("json", "Text contains too many JSON candidates", "TOO_MANY_CANDIDATES")
        try:
            value, end = decoder.raw_decode(text, index)
        except (json.JSONDecodeError, RecursionError):
            continue
        try:
            jsonschema.validate(instance=value, schema=schema)
        except jsonschema.ValidationError:
            continue
        except (jsonschema.SchemaError, RecursionError):
            return _failure("json", "The supplied JSON Schema is invalid", "INVALID_SCHEMA")
        return {"success": True, "data": value, "source": text[index:end], "error": None, "errorCode": None}
    return _failure("json", "No JSON value matched the supplied schema", "NO_MATCH" if candidateCount else "NO_JSON")


@action_handler("A2Q9B4", "Extracting structured XML")
def _extractXml(text: str) -> dict[str, Any]:
    if not _validText(text):
        return _failure("xml", "XML text must be non-empty and within the supported size", "INVALID_TEXT")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        return _failure("xml", "DTD and entity declarations are not supported", "INVALID_XML")
    try:
        root = ET.fromstring(text)
        data = _xmlValue(root, 0)
        return {"success": True, "data": {root.tag: data}, "error": None, "errorCode": None}
    except (ET.ParseError, RecursionError, ValueError):
        return _failure("xml", "XML could not be parsed", "INVALID_XML")


def _xmlValue(element: ET.Element, depth: int) -> Any:
    if depth > 32:
        raise ValueError("XML nesting limit exceeded")
    children = list(element)
    if not children and not element.attrib:
        return (element.text or "").strip()
    result: dict[str, Any] = {}
    if element.attrib:
        result["@attributes"] = dict(element.attrib)
    if element.text and element.text.strip():
        result["#text"] = element.text.strip()
    for child in children:
        value = _xmlValue(child, depth + 1)
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(value)
        else:
            result[child.tag] = value
    return result


@action_handler("A5Z1K7", "Extracting structured YAML")
def _extractYaml(text: str) -> dict[str, Any]:
    if not _validText(text):
        return _failure("yaml", "YAML text must be non-empty and within the supported size", "INVALID_TEXT")
    try:
        import yaml
    except ImportError:
        return _failure("yaml", "PyYAML is not installed", "DEPENDENCY_MISSING")
    try:
        if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for token in yaml.scan(text)):
            return _failure("yaml", "YAML aliases and anchors are not supported", "INVALID_YAML")
        data = yaml.safe_load(text)
        json.dumps(data)
        return {"success": True, "data": data, "error": None, "errorCode": None}
    except (ValueError, TypeError, RecursionError):
        return _failure("yaml", "YAML could not be parsed as JSON-compatible data", "INVALID_YAML")
    except yaml.YAMLError:
        return _failure("yaml", "YAML could not be parsed", "INVALID_YAML")


@action_handler("A9L3F6", "Extracting structured CSV")
def _extractCsv(text: str) -> dict[str, Any]:
    if not _validText(text):
        return _failure("csv", "CSV text must be non-empty and within the supported size", "INVALID_TEXT")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = reader.fieldnames or []
        if not headers:
            return _failure("csv", "CSV must include a header row", "INVALID_CSV")
        rows = []
        for row in reader:
            if len(rows) >= MAX_CSV_ROWS:
                return _failure("csv", f"CSV exceeds the {MAX_CSV_ROWS}-row limit", "TOO_MANY_ROWS")
            rows.append(row)
        return {"success": True, "data": {"headers": headers, "rows": rows}, "error": None, "errorCode": None}
    except (csv.Error, UnicodeError):
        return _failure("csv", "CSV could not be parsed", "INVALID_CSV")


def _validText(text: Any) -> bool:
    return isinstance(text, str) and bool(text.strip()) and len(text) <= MAX_TEXT_CHARS


def _failure(operation: str, error: str, errorCode: str) -> dict[str, Any]:
    return {"success": False, "operation": operation, "data": None, "error": error, "errorCode": errorCode}


def _containsReference(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in {"$ref", "$dynamicRef", "$recursiveRef"} or _containsReference(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_containsReference(child) for child in value)
    return False


_OPERATIONS = {"json": _extractJson, "xml": _extractXml, "yaml": _extractYaml, "csv": _extractCsv}


def extract(operation: str, **arguments: Any) -> dict[str, Any]:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return _failure(operation, "Unsupported extraction operation", "INVALID_OPERATION")
    return handler(**arguments)


def _actionFactory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = _OPERATIONS.get(arguments.get("operation"))
    if handler is None:
        raise ValueError(f"Unsupported extraction operation: {arguments.get('operation')}")
    return handler.__forge_action_factory__(tool_name, arguments)


setattr(extract, "__forge_action_factory__", _actionFactory)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "extract",
        "description": "Parse JSON, XML, YAML, or CSV already supplied as text. Use for structured text, not files or natural-language extraction.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "text": {"type": "string", "maxLength": MAX_TEXT_CHARS},
                "schema": {"type": "object"},
            },
            "required": ["operation"],
            "allOf": [
                {"if": {"properties": {"operation": {"const": operation}}}, "then": {"required": required}}
                for operation, required in {
                    "json": ["text", "schema"], "xml": ["text"], "yaml": ["text"], "csv": ["text"],
                }.items()
            ],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"extract": extract}
