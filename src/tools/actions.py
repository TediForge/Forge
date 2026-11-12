"""Handler-owned Action descriptors for registered tools."""

from collections.abc import Callable, Mapping
from typing import Any


ActionFactory = Callable[[str, Mapping[str, Any]], dict[str, Any]]


def action_handler(action_id: str, message: str, action_type: str = "tool"):
    def decorate(handler):
        def action_factory(tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
            return {
                "actionId": action_id,
                "actionType": action_type,
                "toolName": tool_name,
                "message": message,
                "metadata": {},
            }

        setattr(handler, "__forge_action_factory__", action_factory)
        return handler

    return decorate
