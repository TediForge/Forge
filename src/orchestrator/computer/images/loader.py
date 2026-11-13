"""Strict loader for computer guest environment manifests."""

import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_MANIFEST_ROOT = Path(__file__).with_name("manifests")
_PACKAGE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+_.-]{0,127}\Z")
_USER_PATTERN = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
_SUPPORTED_VERSIONS = {
    "python": {"3.11"},
    "node": {"20"},
    "php": {"8.2"},
    "go": {"1.22"},
}
_WORKSPACE_PATH = re.compile(r"/(?:workspace(?:/[A-Za-z0-9_.-]+)*|tmp)\Z")

PackageName = Annotated[str, Field(min_length=1, max_length=128)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OSManifest(StrictModel):
    base: Literal["ubuntu:22.04"]
    arch: Literal["x86_64"]


class PythonRuntime(StrictModel):
    version: str
    packages: list[Literal["pip", "venv"]] = Field(default_factory=list)
    global_pip: list[PackageName] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value not in _SUPPORTED_VERSIONS["python"]:
            raise ValueError(f"Unsupported Python version: {value}")
        return value

    @field_validator("global_pip")
    @classmethod
    def valid_package_names(cls, values: list[str]) -> list[str]:
        if any(_PACKAGE_PATTERN.fullmatch(value) is None for value in values):
            raise ValueError("Package names contain unsupported characters")
        return values

    @model_validator(mode="after")
    def requires_pip_and_venv(self) -> "PythonRuntime":
        if len(self.packages) != 2 or set(self.packages) != {"pip", "venv"}:
            raise ValueError("Python runtime must include both pip and venv packages")
        return self


class NodeRuntime(StrictModel):
    version: str
    global_npm: list[PackageName] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value not in _SUPPORTED_VERSIONS["node"]:
            raise ValueError(f"Unsupported Node.js version: {value}")
        return value

    @field_validator("global_npm")
    @classmethod
    def valid_package_names(cls, values: list[str]) -> list[str]:
        if any(_PACKAGE_PATTERN.fullmatch(value) is None for value in values):
            raise ValueError("Package names contain unsupported characters")
        return values


class PHPRuntime(StrictModel):
    version: str
    extensions: list[Literal["mbstring", "xml", "curl"]] = Field(default_factory=list)
    composer: bool = False

    @field_validator("version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value not in _SUPPORTED_VERSIONS["php"]:
            raise ValueError(f"Unsupported PHP version: {value}")
        return value


class GoRuntime(StrictModel):
    version: str

    @field_validator("version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value not in _SUPPORTED_VERSIONS["go"]:
            raise ValueError(f"Unsupported Go version: {value}")
        return value


class RuntimeManifest(StrictModel):
    python: PythonRuntime | None = None
    node: NodeRuntime | None = None
    php: PHPRuntime | None = None
    go: GoRuntime | None = None

    @model_validator(mode="after")
    def has_runtime(self) -> "RuntimeManifest":
        if not any((self.python, self.node, self.php, self.go)):
            raise ValueError("At least one runtime must be selected")
        return self


class UserManifest(StrictModel):
    name: str = "agent"
    uid: int = Field(default=1000, ge=1000, le=60000)
    sudo: Literal[False] = False

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if _USER_PATTERN.fullmatch(value) is None:
            raise ValueError("User name contains unsupported characters")
        return value


class ComputerImageManifest(StrictModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=256)
    os: OSManifest
    system_packages: list[PackageName]
    runtimes: RuntimeManifest
    directories: list[str] = Field(min_length=1)
    user: UserManifest = Field(default_factory=UserManifest)

    @field_validator("name")
    @classmethod
    def valid_image_name(cls, value: str) -> str:
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value) is None:
            raise ValueError("Image name must be lowercase alphanumeric with optional hyphens")
        return value

    @field_validator("system_packages")
    @classmethod
    def valid_system_packages(cls, values: list[str]) -> list[str]:
        if any(_PACKAGE_PATTERN.fullmatch(value) is None for value in values):
            raise ValueError("System package names contain unsupported characters")
        return values

    @field_validator("directories")
    @classmethod
    def valid_directories(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(
            _WORKSPACE_PATH.fullmatch(value) is None or ".." in value.split("/")
            for value in values
        ):
            raise ValueError("Directories must be unique paths under /workspace or /tmp")
        return values


Manifest = ComputerImageManifest


def load_manifest(name: str) -> Manifest:
    """Load a named bundled JSON manifest; names cannot select arbitrary files."""
    if not isinstance(name, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name) is None:
        raise ValueError("Manifest name must be lowercase alphanumeric with optional hyphens")
    path = _MANIFEST_ROOT / f"{name}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Computer image manifest not found: {name}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Computer image manifest is invalid JSON: {name}") from exc
    return Manifest.model_validate(payload)
