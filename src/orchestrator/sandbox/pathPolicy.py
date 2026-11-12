"""Policy-backed filesystem boundary shared by local tools."""

import json
import time
from pathlib import Path
from typing import Any

from orchestrator.settings import get_settings


class SandboxPathError(ValueError):
	pass


def _sandboxRoot() -> Path:
	return get_settings().resolved_sandbox_root


def _loadPolicy() -> tuple[Path, dict[str, Any]]:
	root = _sandboxRoot()
	policyPath = root / "policy.json"
	try:
		policy = json.loads(policyPath.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError) as exc:
		raise SandboxPathError("Sandbox policy is unavailable or invalid") from exc
	return root, policy


def _resolveRoots(sandboxRoot: Path, configuredRoots: list[str]) -> list[Path]:
	roots = []
	for configuredRoot in configuredRoots:
		root = (sandboxRoot / configuredRoot).resolve()
		if root == sandboxRoot or root.is_relative_to(sandboxRoot):
			roots.append(root)
	return roots


def safePath(path: str, mode: str = "read", *, isDirectory: bool = False) -> Path:
	"""Resolve a tool path under sandbox policy; never trusts model-provided roots."""
	if mode not in {"read", "write"}:
		raise SandboxPathError("Path mode must be read or write")
	if not isinstance(path, str) or not path.strip() or "\x00" in path:
		raise SandboxPathError("A valid sandbox-relative path is required")
	sandboxRoot, policy = _loadPolicy()
	workspaceRoots = _resolveRoots(sandboxRoot, policy.get("allowedRoots", []))
	writeRoots = _resolveRoots(sandboxRoot, policy.get("writeRoots", []))
	readOnlyRoots = _resolveRoots(sandboxRoot, policy.get("readOnlyRoots", []))
	if not workspaceRoots:
		raise SandboxPathError("Sandbox workspace root is not configured")

	supplied = Path(path.replace("\\", "/")).expanduser()
	candidate = supplied if supplied.is_absolute() else workspaceRoots[0] / supplied
	resolved = candidate.resolve(strict=False)
	allowedRoots = writeRoots if mode == "write" else workspaceRoots
	if not any(resolved.is_relative_to(root) for root in allowedRoots):
		raise SandboxPathError("Path is outside the configured sandbox workspace")
	if mode == "write" and any(resolved == root or resolved.is_relative_to(root) for root in readOnlyRoots):
		raise SandboxPathError("Uploads are read-only")
	if not isDirectory:
		extension = resolved.suffix.casefold()
		allowedExtensions = {item.casefold() for item in policy.get("allowedExtensions", [])}
		forbiddenExtensions = {item.casefold() for item in policy.get("forbiddenExtensions", [])}
		if extension in forbiddenExtensions or extension not in allowedExtensions:
			raise SandboxPathError("File extension is not allowed by sandbox policy")
		if mode == "read" and resolved.is_file():
			maxBytes = int(policy.get("maxFileSizeMb", 50)) * 1024 * 1024
			if resolved.stat().st_size > maxBytes:
				raise SandboxPathError("File exceeds the sandbox size limit")
	return resolved


def workspacePath(*parts: str) -> Path:
	"""Return a trusted workspace path selected by the runtime, not the model."""
	sandboxRoot, policy = _loadPolicy()
	workspaceRoots = _resolveRoots(sandboxRoot, policy.get("allowedRoots", []))
	if not workspaceRoots:
		raise SandboxPathError("Sandbox workspace root is not configured")
	return workspaceRoots[0].joinpath(*parts).resolve()


def workspaceRelativePath(path: str | Path) -> str:
	"""Format a validated workspace path without exposing its host absolute path."""
	sandboxRoot, policy = _loadPolicy()
	workspaceRoots = _resolveRoots(sandboxRoot, policy.get("allowedRoots", []))
	resolved = Path(path).resolve(strict=False)
	for root in workspaceRoots:
		if resolved.is_relative_to(root):
			return str(resolved.relative_to(root))
	raise SandboxPathError("Path is outside the configured sandbox workspace")


def cleanupTmp(now: float | None = None) -> int:
	"""Delete temporary files older than the configured retention period."""
	sandboxRoot, policy = _loadPolicy()
	tmpRoots = _resolveRoots(sandboxRoot, policy.get("temporaryRoots", []))
	if not tmpRoots:
		return 0
	root = tmpRoots[0]
	root.mkdir(parents=True, exist_ok=True)
	retentionHours = max(1, int(policy.get("cleanupTmpAfterHours", 24)))
	cutoff = (now if now is not None else time.time()) - retentionHours * 3600
	removed = 0
	for entry in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
		try:
			if entry.is_symlink():
				entry.unlink()
				removed += 1
			elif entry.is_file() and entry.stat().st_mtime < cutoff:
				entry.unlink()
				removed += 1
			elif entry.is_dir() and entry.stat().st_mtime < cutoff and not any(entry.iterdir()):
				entry.rmdir()
		except OSError:
			continue
	return removed