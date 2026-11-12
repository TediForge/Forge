"""Clock and timezone tools."""

from datetime import datetime
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from src.tools.actions import action_handler


@action_handler("A9C5J8", "Checking the current time")
def clock(
    operation: str,
    timezone: str = "UTC",
    from_timezone: str = "UTC",
    to_timezone: str = "UTC",
    timestamp: str = "",
) -> dict:
    if operation == "convert":
        return _convert(from_timezone=from_timezone, to_timezone=to_timezone, timestamp=timestamp)
    if operation != "now":
        return {
            "success": False, "operation": operation, "timezone": timezone, "iso": None,
            "date": None, "time": None, "weekday": None,
            "error": "Unsupported clock operation", "errorCode": "INVALID_OPERATION",
        }
    if not isinstance(timezone, str) or not timezone.strip():
        return {
            "success": False, "timezone": str(timezone), "iso": None,
            "date": None, "time": None, "weekday": None,
            "error": "Timezone must be a non-empty IANA timezone name",
            "errorCode": "INVALID_TIMEZONE",
        }
    try:
        now = datetime.now(ZoneInfo(timezone.strip()))
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return {
            "success": False, "timezone": timezone, "iso": None,
            "date": None, "time": None, "weekday": None,
            "error": f"Unknown timezone: {timezone}",
            "errorCode": "INVALID_TIMEZONE",
        }
    return {
        "success": True,
        "timezone": timezone.strip(),
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "error": None,
        "errorCode": None,
    }


@action_handler("A7T4M1", "Converting a time between timezones")
def _convert(from_timezone: str = "UTC", to_timezone: str = "UTC", timestamp: str = "") -> dict:
    result = {
        "success": False, "timezone": to_timezone, "iso": None, "date": None,
        "time": None, "weekday": None, "error": None, "errorCode": None,
    }
    if not isinstance(timestamp, str) or not timestamp.strip():
        result.update(error="An ISO 8601 timestamp is required", errorCode="INVALID_TIMESTAMP")
        return result
    try:
        sourceZone = ZoneInfo(from_timezone)
        targetZone = ZoneInfo(to_timezone)
        sourceTime = datetime.fromisoformat(timestamp)
        if sourceTime.tzinfo is None:
            sourceTime = sourceTime.replace(tzinfo=sourceZone)
        converted = sourceTime.astimezone(targetZone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        result.update(error="Timestamp or timezone is invalid", errorCode="INVALID_TIMEZONE")
        return result
    result.update({
        "success": True,
        "iso": converted.isoformat(),
        "date": converted.strftime("%Y-%m-%d"),
        "time": converted.strftime("%H:%M:%S"),
        "weekday": converted.strftime("%A"),
    })
    return result


_NOW_ACTION_FACTORY = clock.__forge_action_factory__


def _action_factory(tool_name: str, arguments: dict) -> dict:
    operation = arguments.get("operation")
    handlers = {"now": _NOW_ACTION_FACTORY, "convert": _convert.__forge_action_factory__}
    factory = handlers.get(operation)
    if factory is None:
        raise ValueError(f"Unsupported clock operation: {operation}")
    return factory(tool_name, arguments)


setattr(clock, "__forge_action_factory__", _action_factory)


TOOLS = [{
    "type": "function",
    "function": {
        "name": "clock",
        "description": (
            "Get the current date, time, and weekday in a timezone. Use whenever an answer needs "
            "accurate current time, such as answering what time it is or timestamping an event; "
            "do not guess from training data. Use a valid IANA timezone such as "
            "'America/New_York', 'Europe/London', or 'Asia/Tokyo'. Defaults to UTC."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["now", "convert"]},
                "timezone": {"type": "string", "default": "UTC", "description": "IANA timezone name, for example 'Asia/Tokyo'."},
                "from_timezone": {"type": "string", "default": "UTC"},
                "to_timezone": {"type": "string", "default": "UTC"},
                "timestamp": {"type": "string", "description": "ISO 8601 timestamp; a timezone-naive value is interpreted in from_timezone."},
            },
            "required": ["operation"],
            "allOf": [{
                "if": {"properties": {"operation": {"const": "convert"}}},
                "then": {"required": ["from_timezone", "to_timezone", "timestamp"]},
            }],
            "additionalProperties": False,
        },
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "timezone": {"type": "string"},
            "iso": {"type": ["string", "null"]},
            "date": {"type": ["string", "null"]},
            "time": {"type": ["string", "null"]},
            "weekday": {"type": ["string", "null"]},
            "error": {"type": ["string", "null"]},
            "errorCode": {"type": ["string", "null"]},
        },
        "required": ["success", "timezone", "iso", "date", "time", "weekday", "error", "errorCode"],
        "additionalProperties": False,
    },
}]
HANDLERS = {"clock": clock}
