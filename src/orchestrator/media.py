"""Shared utilities for converting trusted media into bounded inline payloads."""

import base64
import hashlib
import ipaddress
import mimetypes
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from orchestrator.settings import get_settings


class MediaConversionError(ValueError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InlineMedia:
    mediaData: str
    mimeType: str
    fileName: str
    fileSizeBytes: int
    sha256: str


class MediaConverter:
    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        max_bytes: int = 20 * 1024 * 1024,
        allowed_hosts: list[str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._http = http_client or httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False)
        self._owns_client = http_client is None
        self._max_bytes = max_bytes
        settings = get_settings()
        self._allowed_hosts = {
            host.strip().casefold()
            for host in (allowed_hosts if allowed_hosts is not None else settings.allowed_media_hosts)
            if host.strip()
        }

    @classmethod
    def from_environment(cls) -> "MediaConverter":
        return cls(max_bytes=get_settings().media_max_bytes)

    async def fromUrl(
        self,
        url: str,
        fileName: str | None = None,
        max_bytes: int | None = None,
    ) -> InlineMedia:
        byteLimit = min(max_bytes, self._max_bytes) if max_bytes is not None else self._max_bytes
        if byteLimit < 1:
            raise ValueError("max_bytes must be positive")
        try:
            parts = urlsplit(url)
            port = parts.port or 443
        except ValueError as exc:
            raise MediaConversionError("Media URL is invalid", "INVALID_URL") from exc
        host = (parts.hostname or "").casefold()
        if parts.scheme != "https" or not host or parts.username or parts.password:
            raise MediaConversionError("Media URL must be an HTTPS URL without credentials", "INVALID_URL")
        if host not in self._allowed_hosts:
            raise MediaConversionError("Media host is not allowed", "HOST_NOT_ALLOWED")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise MediaConversionError("Media host could not be resolved", "FETCH_FAILED") from exc
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise MediaConversionError("Media host resolves to a non-public address", "HOST_NOT_ALLOWED")

        try:
            async with self._http.stream("GET", url) as response:
                if response.status_code != 200:
                    raise MediaConversionError("Media fetch failed", "FETCH_FAILED")
                declared_size = response.headers.get("content-length")
                if declared_size and int(declared_size) > byteLimit:
                    raise MediaConversionError("Media exceeds configured size limit", "TOO_LARGE")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > byteLimit:
                        raise MediaConversionError("Media exceeds configured size limit", "TOO_LARGE")
                filename = fileName or Path(parts.path).name or "asset"
                mime = response.headers.get("content-type", "").split(";", 1)[0].strip()
                inline = self._inline(
                    bytes(body),
                    mime or mimetypes.guess_type(filename)[0] or "application/octet-stream",
                    filename,
                )
                if inline.fileSizeBytes > byteLimit:
                    raise MediaConversionError("Media exceeds configured size limit", "TOO_LARGE")
                return inline
        except MediaConversionError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise MediaConversionError("Media fetch failed", "FETCH_FAILED") from exc

    def fromFile(self, path: str | Path, fileName: str | None = None) -> InlineMedia:
        source = Path(path)
        if not source.is_file():
            raise MediaConversionError("Media file was not found", "FILE_NOT_FOUND")
        if source.stat().st_size > self._max_bytes:
            raise MediaConversionError("Media exceeds configured size limit", "TOO_LARGE")
        raw = source.read_bytes()
        return self._inline(raw, mimetypes.guess_type(source.name)[0] or "application/octet-stream", fileName or source.name)

    def fromBase64(self, mediaData: str, mimeType: str, fileName: str) -> InlineMedia:
        try:
            raw = base64.b64decode(mediaData, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise MediaConversionError("Media is not valid base64", "INVALID_BASE64") from exc
        if len(raw) > self._max_bytes:
            raise MediaConversionError("Media exceeds configured size limit", "TOO_LARGE")
        return self._inline(raw, mimeType, fileName)

    def _inline(self, raw: bytes, mimeType: str, fileName: str) -> InlineMedia:
        if len(raw) > self._max_bytes:
            raise MediaConversionError("Media exceeds configured size limit", "TOO_LARGE")
        signatures = {
            "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
            "image/webp": len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
            "application/pdf": raw.startswith(b"%PDF-"),
            "audio/wav": raw.startswith(b"RIFF") and raw[8:12] == b"WAVE",
            "audio/ogg": raw.startswith(b"OggS"),
            "audio/mpeg": raw.startswith(b"ID3") or raw[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"},
        }
        if mimeType in signatures and not signatures[mimeType]:
            raise MediaConversionError("Media bytes do not match the declared MIME type", "MIME_MISMATCH")
        return InlineMedia(
            mediaData=base64.b64encode(raw).decode("ascii"),
            mimeType=mimeType,
            fileName=fileName,
            fileSizeBytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._http.aclose()
