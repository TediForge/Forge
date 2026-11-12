# Injects ambient environmental context into orchestrator runs

from datetime import datetime, timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class RuntimeContext:
    @staticmethod
    def getAmbientContext(timezone: str = "UTC") -> dict:
        """
        Returns ambient system context, injecting date and time
        so the model has native temporal awareness.
        """
        if timezone.upper() in {"UTC", "GMT", "Z", "ETC/UTC"}:
            now = datetime.now(datetime_timezone.utc)
            resolved_timezone = "UTC"
        else:
            try:
                zone = ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"Unknown timezone: {timezone}") from exc
            now = datetime.now(zone)
            resolved_timezone = timezone

        return {
            "currentDate": now.strftime("%Y-%m-%d"),
            "currentTime": now.strftime("%H:%M:%S %Z"),
            "dayOfWeek": now.strftime("%A"),
            "timezone": resolved_timezone,
            "environment": "production",
            "orchestrator": "Forge"
        }