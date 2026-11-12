# Manages conversation history and message windows for the active session

from typing import List, Dict, Any
from pydantic import BaseModel


class SessionManager:
    def __init__(self, sessionId: str, history: List[Dict[str, Any]] = None):
        self.sessionId = sessionId
        self.history = [
            message.model_dump(by_alias=True) if isinstance(message, BaseModel) else dict(message)
            for message in (history or [])
        ]

    def addMessage(self, role: str, content: str):
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError(f"Unsupported message role: {role}")
        if not isinstance(content, str):
            raise TypeError("Message content must be a string")
        self.history.append({"role": role, "content": content})

    def getFormattedHistory(self) -> List[Dict[str, str]]:
        """Returns history formatted for model ingestion."""
        return self.history

    def recent(self, n: int = 10) -> List[Dict[str, Any]]:
        if n < 0:
            raise ValueError("n must be non-negative")
        messages = self.history[-n:] if n else []
        return [
            {
                **{key: value for key, value in message.items() if key != "attachments"},
                "attachments": [
                    {"fileName": item.get("fileName", "attachment")}
                    for item in message.get("attachments", [])
                    if isinstance(item, dict)
                ],
            }
            for message in messages
        ]

    def prompt_block(self, max_chars: int = 8000) -> str:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        messages = self.recent(10)
        if not messages:
            return ""
        lines: list[str] = []
        remaining = max_chars
        for message in reversed(messages):
            role = str(message.get("role", "user"))
            text = str(message.get("content", ""))[:2000]
            attachment_names = [
                str(item.get("fileName", "attachment"))
                for item in message.get("attachments", [])
                if isinstance(item, dict)
            ]
            if attachment_names:
                text = f"{text}\n[attachments: {', '.join(attachment_names)}]"
            line = f"{role}: {text}"
            if len(line) > remaining:
                line = line[:remaining]
            if not line:
                break
            lines.append(line)
            remaining -= len(line) + 1
            if remaining <= 0:
                break
        return "## Conversation so far\n" + "\n".join(reversed(lines))