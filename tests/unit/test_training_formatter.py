from src.export.formatters import format_openai_chat_jsonl


def test_openai_chat_jsonl_has_only_user_and_assistant_messages():
    assert format_openai_chat_jsonl("hello", "world") == {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
    }


def test_openai_chat_jsonl_preserves_unicode_without_system_message():
    record = format_openai_chat_jsonl("你好", "café")
    assert record["messages"][0]["content"] == "你好"
    assert record["messages"][1]["content"] == "café"
    assert all(message["role"] != "system" for message in record["messages"])
