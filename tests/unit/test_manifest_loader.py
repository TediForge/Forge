import pytest
from pydantic import ValidationError

from orchestrator.computer.images.builder import _generate_dockerfile
from orchestrator.computer.images.loader import ComputerImageManifest, load_manifest


def test_base_manifest_loads_all_configured_runtimes() -> None:
    manifest = load_manifest("base")

    assert manifest.name == "forge-base"
    assert manifest.os.base == "ubuntu:22.04"
    assert manifest.runtimes.python.version == "3.11"
    assert manifest.runtimes.node.version == "20"
    assert manifest.runtimes.php.version == "8.2"
    assert manifest.runtimes.go.version == "1.22"
    assert manifest.user.name == "agent"
    assert manifest.user.sudo is False


def test_python_only_manifest_is_valid() -> None:
    manifest = load_manifest("python-only")

    assert manifest.runtimes.python is not None
    assert manifest.runtimes.node is None
    assert manifest.runtimes.php is None
    assert manifest.runtimes.go is None


def test_loader_rejects_unknown_manifest_name() -> None:
    with pytest.raises(ValueError, match="Manifest name"):
        load_manifest("../base")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unexpected", True),
        ("user", {"name": "agent", "uid": 1000, "sudo": True}),
        ("directories", ["/workspace", "/etc"]),
    ],
)
def test_manifest_rejects_unknown_fields_and_unsafe_values(field: str, value: object) -> None:
    raw = load_manifest("base").model_dump(mode="json")
    raw[field] = value

    with pytest.raises(ValidationError):
        ComputerImageManifest.model_validate(raw)


def test_manifest_rejects_unsupported_versions_and_shell_metacharacters() -> None:
    raw = load_manifest("base").model_dump(mode="json")
    raw["runtimes"]["python"]["version"] = "3.12"
    with pytest.raises(ValidationError, match="Unsupported Python version"):
        ComputerImageManifest.model_validate(raw)

    raw["runtimes"]["python"]["version"] = "3.11"
    raw["system_packages"].append("curl;touch /tmp/pwned")
    with pytest.raises(ValidationError, match="unsupported characters"):
        ComputerImageManifest.model_validate(raw)


def test_generated_dockerfile_installs_runtime_and_guest_agent() -> None:
    manifest = load_manifest("base")
    dockerfile = _generate_dockerfile(manifest)

    assert dockerfile.startswith("FROM golang:1.22 AS forge-go")
    assert "node_20.x" in dockerfile
    assert "php8.2-mbstring" in dockerfile
    assert "python3.11 -m venv /opt/forge-python" in dockerfile
    assert "COPY --from=forge-go /usr/local/go /usr/local/go" in dockerfile
    assert "COPY computer_guest.py /usr/local/lib/forge/computer_guest.py" in dockerfile
    assert "/dev/vda / ext4 ro 0 1" in dockerfile
    assert "{{" not in dockerfile
