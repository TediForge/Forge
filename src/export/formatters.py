"""OpenAI-compatible JSONL formatting for completed run pairs."""

from typing import Any


def format_openai_chat_jsonl(prompt: str, final_response: str) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": final_response},
        ]
    }
