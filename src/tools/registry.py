"""Registry for Forge tool definitions and executors."""

from importlib import import_module
import inspect
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from src.skills.loader import loadSkillMeta


ToolHandler = Callable[..., Any]


class ToolRegistry:
    """Stores OpenAI-compatible tool schemas and their Python handlers."""

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, ToolHandler] = {}

    def register_module(self, module_name: str) -> None:
        module = import_module(module_name)
        tools = getattr(module, "TOOLS", ())
        handlers = getattr(module, "HANDLERS", {})

        for tool in tools:
            function = tool.get("function", tool)
            name = function["name"]
            handler = handlers.get(name)
            if handler is None:
                raise ValueError(f"Tool '{name}' has no registered handler")
            self.register(name, tool, handler)

    def register(self, name: str, definition: Mapping[str, Any], handler: ToolHandler) -> None:
        if re.fullmatch(r"[a-z][a-z0-9]*", name) is None:
            raise ValueError(f"Tool name must be one lowercase word: {name}")
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        loadSkillMeta(name, "tools")
        self._tools[name] = dict(definition)
        self._handlers[name] = handler

    def definitions(self) -> List[Dict[str, Any]]:
        return [self._tools[name] for name in sorted(self._tools)]

    def names(self) -> List[str]:
        return sorted(self._tools)

    def execute(self, name: str, arguments: Optional[Mapping[str, Any]] = None) -> Any:
        if name not in self._handlers:
            raise KeyError(f"Unknown tool: {name}")
        return self._handlers[name](**dict(arguments or {}))

    async def executeAsync(self, name: str, arguments: Optional[Mapping[str, Any]] = None) -> Any:
        result = self.execute(name, arguments)
        return await result if inspect.isawaitable(result) else result

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self._tools.get(name)

    def actionFor(self, name: str, arguments: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        if name not in self._handlers:
            raise KeyError(f"Unknown tool: {name}")
        values = arguments or {}
        factory = getattr(self._handlers[name], "__forge_action_factory__", None)
        if not callable(factory):
            raise ValueError(f"Tool '{name}' has no handler-owned Action descriptor")
        action = factory(name, values)
        if not isinstance(action, dict):
            raise TypeError(f"Tool '{name}' Action descriptor must be an object")
        return action


DEFAULT_MODULES = (
    "src.tools.definitions.audio",
    "src.tools.definitions.calculator",
    "src.tools.definitions.clock",
    "src.tools.definitions.data",
    "src.tools.definitions.extract",
    "src.tools.definitions.fetch",
    "src.tools.definitions.generate",
    "src.tools.definitions.image",
    "src.tools.definitions.pdf",
    "src.tools.definitions.search",
    "src.tools.definitions.spreadsheet",
    "src.tools.definitions.speak",
    "src.tools.definitions.summarize",
    "src.tools.definitions.transcribe",
    "src.tools.definitions.translate",
    "src.tools.definitions.video",
    "src.tools.definitions.weather",
)

def create_default_registry(extra_modules: Iterable[str] = ()) -> ToolRegistry:
    registry = ToolRegistry()
    for module_name in (*DEFAULT_MODULES, *extra_modules):
        registry.register_module(module_name)
    return registry
