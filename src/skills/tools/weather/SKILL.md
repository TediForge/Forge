---
name: weather
description: Use to retrieve current weather or a short forecast from Open-Meteo; do not use without an approved location.
category: tool
---

# Weather

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `current` | Retrieve current conditions | `latitude`, `longitude` | implemented |
| `forecast` | Retrieve a short forecast | `latitude`, `longitude`; optional `days` | implemented |

## When to use
- The user asks for live weather and provides or approves a location.
- Coordinates are available from an explicitly supplied location.
- A forecast of one to seven days is requested.

## When not to use
- Do not use without a user-provided or approved location.
- Do not use for climate history; use a historical source.
- Do not infer live conditions from model knowledge.

## How to call
Call `weather(operation="current", latitude, longitude)` or `weather(operation="forecast", latitude, longitude, days=3)`. Location names must be resolved outside this tool; the provider receives coordinates only.

## Examples
1. Current conditions: `weather(operation="current", latitude=37.77, longitude=-122.42)`.
2. Three-day forecast: `weather(operation="forecast", latitude=37.77, longitude=-122.42, days=3)`.
3. Seven-day forecast: set `days=7` when requested.
4. Confirm the location before translating a place name into coordinates.
5. Wrong operation returns `INVALID_OPERATION`.
6. For climate information, distinguish historical patterns from live weather.

## Edge cases
- **Provider timeout/unavailable:** report the provider error; do not fabricate conditions.
- **Unknown operation:** report `INVALID_OPERATION`.
- **Missing coordinates:** do not infer a location.
- **Coordinates out of range:** report `INVALID_COORDINATES`.
- **Invalid forecast length:** report `INVALID_LIMIT`.
- **Invalid provider payload:** report `INVALID_PROVIDER_RESULT`.
- **Current conditions:** never imply stale model data is live.
- **Forecast period:** do not make a forecast without a provider.
