from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
PROHIBITED_INFERENCE_HOSTS = (
    "router.huggingface.co",
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
)


def test_model_and_tool_sources_do_not_call_remote_inference():
    for root in (
        SOURCE_ROOT / "orchestrator" / "engine",
        SOURCE_ROOT / "orchestrator" / "tools",
    ):
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for host in PROHIBITED_INFERENCE_HOSTS:
                assert host not in source, f"{host} found in {path}"


def test_huggingface_hub_calls_are_isolated_to_the_source_layer():
    source = (SOURCE_ROOT / "orchestrator" / "inference" / "sources" / "huggingface.py").read_text(
        encoding="utf-8",
    )
    assert "snapshot_download" in source
    assert "httpx" not in source
    for path in (SOURCE_ROOT / "orchestrator" / "engine").rglob("*.py"):
        assert "huggingface_hub" not in path.read_text(encoding="utf-8")
        assert "transformers" not in path.read_text(encoding="utf-8")


def test_serving_code_does_not_import_offline_rl_package():
    serving_roots = (
        SOURCE_ROOT / "orchestrator" / "api",
        SOURCE_ROOT / "orchestrator" / "engine",
        SOURCE_ROOT / "orchestrator" / "inference",
        SOURCE_ROOT / "orchestrator" / "tools",
    )
    for root in serving_roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "orchestrator.rl" not in source, f"RL imported by serving code: {path}"
