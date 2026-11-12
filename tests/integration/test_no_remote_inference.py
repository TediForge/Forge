from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
PROHIBITED_INFERENCE_HOSTS = (
    "router.huggingface.co",
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
)


def test_model_and_tool_sources_do_not_call_remote_inference():
    for root in (SOURCE_ROOT / "core" / "models", SOURCE_ROOT / "tools"):
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for host in PROHIBITED_INFERENCE_HOSTS:
                assert host not in source, f"{host} found in {path}"


def test_huggingface_runtime_uses_hub_snapshot_download_not_httpx():
    source = (SOURCE_ROOT / "core" / "models" / "huggingface.py").read_text(encoding="utf-8")
    assert "snapshot_download" in source
    assert "httpx" not in source
