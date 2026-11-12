from orchestrator.context.session import SessionManager
from orchestrator.context.state import ExecutionState


def test_history_prompt_includes_recent_turns_with_caps():
    session = SessionManager("s", [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ])
    block = session.prompt_block()
    assert "user: first" in block
    assert "assistant: second" in block
    assert "user: third" in block

    long_history = SessionManager("s", [
        {"role": "user", "content": f"message-{index} " + ("x" * 2500)}
        for index in range(50)
    ])
    capped = long_history.prompt_block()
    assert "message-49" in capped
    assert "message-39" not in capped
    assert len(capped) <= 8000 + len("## Conversation so far\n")


def test_history_attachments_only_contribute_names_and_empty_history_is_empty():
    session = SessionManager("s", [{
        "role": "user",
        "content": "Review this",
        "attachments": [{"fileName": "report.pdf", "fileData": "secret-base64"}],
    }])
    block = session.prompt_block()
    assert "report.pdf" in block
    assert "secret-base64" not in block
    assert SessionManager("empty").prompt_block() == ""


def test_resume_history_snapshot_is_sanitized_and_restorable():
    manager = SessionManager("s", [{
        "role": "user",
        "content": "Prior question",
        "attachments": [{"fileName": "prior.png", "fileData": "private-bytes"}],
    }])
    checkpoint = ExecutionState("r", {"sessionHistory": manager.recent()}).exportState()
    checkpoint["variables"]["sessionHistory"] = manager.recent()
    restored = SessionManager("s", checkpoint["variables"]["sessionHistory"])
    assert "Prior question" in restored.prompt_block()
    assert "prior.png" in restored.prompt_block()
    assert "private-bytes" not in str(checkpoint)
