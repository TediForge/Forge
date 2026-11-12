"""Current weather and forecast operations, including their Open-Meteo client."""

import math
from typing import Any

import httpx

from src.tools.actions import action_handler


class WeatherProviderError(RuntimeError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


class OpenMeteoAdapter:
    async def get(self, operation: str, latitude: float, longitude: float, days: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "auto",
        }
        if operation == "current":
            params["current"] = "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m"
        else:
            params.update(
                daily="temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                forecast_days=days,
            )
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise WeatherProviderError("Weather provider timed out", "PROVIDER_TIMEOUT") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise WeatherProviderError("Weather provider is unavailable", "PROVIDER_UNAVAILABLE") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise WeatherProviderError("Weather provider returned invalid data", "PROVIDER_ERROR")
        return payload


def _failure(operation: str, error: str, errorCode: str) -> dict[str, Any]:
    return {"success": False, "operation": operation, "error": error, "errorCode": errorCode}


@action_handler("A3W2F9", "Checking current weather")
async def _current(latitude: float, longitude: float, provider: OpenMeteoAdapter | None = None) -> dict[str, Any]:
    return await _getWeather("current", latitude, longitude, 1, provider)


@action_handler("A7F6L1", "Checking the weather forecast")
async def _forecast(latitude: float, longitude: float, days: int = 3, provider: OpenMeteoAdapter | None = None) -> dict[str, Any]:
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 7:
        return _failure("forecast", "days must be between 1 and 7", "INVALID_LIMIT")
    return await _getWeather("forecast", latitude, longitude, days, provider)


async def _getWeather(operation: str, latitude: float, longitude: float, days: int, provider: OpenMeteoAdapter | None) -> dict[str, Any]:
    if (
        isinstance(latitude, bool) or isinstance(longitude, bool)
        or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float))
        or not math.isfinite(latitude) or not math.isfinite(longitude)
        or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
    ):
        return _failure(operation, "Latitude and longitude are outside supported ranges", "INVALID_COORDINATES")
    try:
        payload = await (provider or OpenMeteoAdapter()).get(operation, latitude, longitude, days)
    except WeatherProviderError as exc:
        return _failure(operation, str(exc), exc.code)
    value = payload.get("current" if operation == "current" else "daily")
    if not isinstance(value, dict):
        return _failure(operation, "Weather provider omitted the requested data", "INVALID_PROVIDER_RESULT")
    return {
        "success": True, "operation": operation, "latitude": latitude, "longitude": longitude,
        "timezone": payload.get("timezone"), "weather": value,
        "error": None, "errorCode": None,
    }


_OPERATIONS = {"current": _current, "forecast": _forecast}


async def weather(operation: str, **arguments: Any) -> dict[str, Any]:
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return _failure(operation, "Unsupported weather operation", "INVALID_OPERATION")
    return await handler(**arguments)


def _actionFactory(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = _OPERATIONS.get(arguments.get("operation"))
    if handler is None:
        raise ValueError(f"Unsupported weather operation: {arguments.get('operation')}")
    return handler.__forge_action_factory__(tool_name, arguments)


setattr(weather, "__forge_action_factory__", _actionFactory)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "weather",
        "description": "Retrieve current conditions or a short forecast from Open-Meteo using explicit coordinates. Use for local weather requests when the user has supplied or approved a location.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(_OPERATIONS)},
                "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                "longitude": {"type": "number", "minimum": -180, "maximum": 180},
                "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 3},
            },
            "required": ["operation", "latitude", "longitude"],
            "additionalProperties": False,
        },
    },
}]
HANDLERS = {"weather": weather}
