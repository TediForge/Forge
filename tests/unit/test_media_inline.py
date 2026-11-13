import base64
import asyncio
import socket

import pytest

from orchestrator.media import MediaConversionError, MediaConverter
from orchestrator.schemas.v1.responses import ContentBlock, ResponsesInputContent


PNG_DATA = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jO7sAAAAASUVORK5CYII="


def test_base64_media_is_bounded_and_has_no_url_field(monkeypatch):
    converter = MediaConverter(max_bytes=1000)
    inline = converter.fromBase64(PNG_DATA, "image/png", "pixel.png")
    block = ContentBlock(
        type="image",
        mediaData=inline.mediaData,
        mimeType=inline.mimeType,
        fileName=inline.fileName,
        fileSizeBytes=inline.fileSizeBytes,
    )
    serialized = block.model_dump(by_alias=True, exclude_none=True)
    assert serialized["mediaData"] == PNG_DATA
    assert "url" not in serialized
    assert serialized["fileSizeBytes"] == len(base64.b64decode(PNG_DATA))

    monkeypatch.setattr("orchestrator.schemas.v1.responses.models.MAX_MEDIA_BYTES", 1)
    with pytest.raises(ValueError, match="exceeds"):
        ContentBlock(type="image", mediaData=PNG_DATA, mimeType="image/png")
    with pytest.raises(MediaConversionError, match="MIME"):
        converter.fromBase64(PNG_DATA, "image/jpeg", "pixel.png")


def test_responses_media_input_requires_inline_bytes():
    with pytest.raises(ValueError):
        ResponsesInputContent.model_validate({
            "type": "input_image",
            "imageUrl": "https://example.test/image.png",
        })
    media = ResponsesInputContent.model_validate({
        "type": "input_image",
        "mediaData": PNG_DATA,
        "mimeType": "image/png",
    })
    assert media.mediaData == PNG_DATA


def test_online_media_is_fetched_and_inlined_with_host_and_size_limits(monkeypatch):
    raw = base64.b64decode(PNG_DATA)

    class Response:
        status_code = 200
        headers = {"content-type": "image/png", "content-length": str(len(raw))}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

        async def aiter_bytes(self):
            yield raw

    class Client:
        called = False

        def stream(self, method, url):
            self.called = True
            assert method == "GET"
            assert url == "https://assets.example.test/pixel.png"
            return Response()

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    client = Client()
    converter = MediaConverter(
        http_client=client,
        max_bytes=100,
        allowed_hosts=["assets.example.test"],
    )
    inline = asyncio.run(converter.fromUrl(
        "https://assets.example.test/pixel.png",
        max_bytes=100,
    ))
    assert inline.mediaData == PNG_DATA
    assert inline.mimeType == "image/png"
    assert inline.fileSizeBytes == len(raw)
    assert client.called

    blocked_client = Client()
    blocked = MediaConverter(
        http_client=blocked_client,
        max_bytes=100,
        allowed_hosts=["other.example.test"],
    )
    with pytest.raises(MediaConversionError) as error:
        asyncio.run(blocked.fromUrl("https://assets.example.test/pixel.png"))
    assert error.value.code == "HOST_NOT_ALLOWED"
    assert not blocked_client.called


def test_online_media_rejects_malformed_port():
    converter = MediaConverter(allowed_hosts=["assets.example.test"])
    with pytest.raises(MediaConversionError) as error:
        asyncio.run(converter.fromUrl("https://assets.example.test:not-a-port/pixel.png"))
    assert error.value.code == "INVALID_URL"
    asyncio.run(converter.close())
