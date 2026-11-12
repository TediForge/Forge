import asyncio
import base64
import io
from types import SimpleNamespace

from pypdf import PdfWriter
from PIL import Image as PillowImage

from orchestrator.tools.definitions.audio import audio
from orchestrator.tools.definitions.clock import clock
from orchestrator.tools.definitions.extract import extract
from orchestrator.tools.definitions.fetch import fetch
from orchestrator.tools.definitions.generate import generate
from orchestrator.tools.definitions.image import generate as generateImage
from orchestrator.tools.definitions.pdf import pdf
from orchestrator.tools.definitions.search import search
from orchestrator.tools.definitions.spreadsheet import sheet
from orchestrator.tools.definitions.summarize import summarize
from orchestrator.tools.definitions.translate import translate
from orchestrator.tools.definitions.weather import OpenMeteoAdapter, weather


def _blankPdf() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return output.getvalue()


class _MediaProvider:
    async def fromUrl(self, url, fileName=None, max_bytes=None):
        if url.endswith(".pdf"):
            raw, mime = _blankPdf(), "application/pdf"
        elif url.endswith(".json"):
            raw, mime = b'{"ok": true}', "application/json"
        else:
            raw, mime = b"<html><script>ignore()</script><p>Useful page content.</p></html>", "text/html"
        return SimpleNamespace(
            mediaData=base64.b64encode(raw).decode("ascii"),
            mimeType=mime,
        )


def test_fetch_url_json_and_pdf_with_mocked_provider():
    provider = _MediaProvider()
    url = asyncio.run(fetch("url", url="https://example.org/page", mediaConverter=provider))
    payload = asyncio.run(fetch("json", url="https://example.org/data.json", mediaConverter=provider))
    document = asyncio.run(fetch("pdf", url="https://example.org/file.pdf", mediaConverter=provider))

    assert url["success"] is True and "Useful page content." in url["content"]
    assert payload["success"] is True and payload["data"] == {"ok": True}
    assert document["success"] is True and document["pageCount"] == 1


def test_local_pdf_text_extraction_succeeds(sandboxWorkspace):
    source = sandboxWorkspace / "uploads" / "blank.pdf"
    source.write_bytes(_blankPdf())

    result = pdf("text", path="uploads/blank.pdf")

    assert result["success"] is True
    assert result["pageCount"] == 1
    assert result["text"] == ""


def test_url_summary_uses_bounded_page_text():
    result = asyncio.run(summarize(
        "url",
        url="https://example.org/page",
        mediaConverter=_MediaProvider(),
    ))

    assert result["success"] is True
    assert result["summary"] == "Useful page content."
    assert result["url"] == "https://example.org/page"


def test_translation_and_weather_use_injected_providers():
    class TextProvider:
        async def generate(self, prompt, **options):
            assert "French" in prompt
            return "Bonjour."

    class WeatherProvider:
        async def get(self, operation, latitude, longitude, days):
            assert (latitude, longitude) == (37.77, -122.42)
            return {"current": {"temperature_2m": 18}, "daily": {"time": []}, "timezone": "UTC"}

    translation = asyncio.run(translate(
        "text", text="Good morning.", target_language="French", dispatcher=TextProvider(),
    ))
    current = asyncio.run(weather(
        "current", latitude=37.77, longitude=-122.42, provider=WeatherProvider(),
    ))
    forecast = asyncio.run(weather(
        "forecast", latitude=37.77, longitude=-122.42, days=2, provider=WeatherProvider(),
    ))

    assert translation["success"] is True and translation["translation"] == "Bonjour."
    assert current["success"] is True and current["weather"]["temperature_2m"] == 18
    assert forecast["success"] is True and forecast["operation"] == "forecast"


def test_weather_tool_owns_open_meteo_http_client(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"current": {"temperature_2m": 18}, "timezone": "UTC"}

    class Client:
        def __init__(self, **options):
            assert options == {"timeout": 10.0, "follow_redirects": False}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params):
            assert url == "https://api.open-meteo.com/v1/forecast"
            assert params["latitude"] == 10
            assert "current" in params
            return Response()

    monkeypatch.setattr("orchestrator.tools.definitions.weather.httpx.AsyncClient", Client)

    result = asyncio.run(OpenMeteoAdapter().get("current", 10, 20, 1))

    assert result["current"]["temperature_2m"] == 18


def test_search_image_and_news_use_injected_provider():
    class SearchProvider:
        def search(self, operation, query, max_results, extract_results=0):
            return {"results": [{"type": operation}], "errors": []} if operation == "web" else {"results": [{"type": operation}]}

    images = search("image", query="mountains", provider=SearchProvider())
    news = search("news", query="science", provider=SearchProvider())

    assert images["success"] and images["results"] == [{"type": "image"}]
    assert news["success"] and news["results"] == [{"type": "news"}]


def test_audio_generation_uses_local_speech_dispatcher():
    class VoiceProvider:
        async def generate(self, prompt, **options):
            return {"mediaType": "audio", "mediaData": "YXVkaW8=", "mimeType": "audio/wav"}

    result = asyncio.run(generate("audio", prompt="Welcome.", audioDispatcher=VoiceProvider()))

    assert result["success"] is True
    assert result["mediaType"] == "audio"


def test_clock_timezone_conversion_succeeds():
    result = clock(
        "convert",
        from_timezone="Europe/London",
        to_timezone="Asia/Tokyo",
        timestamp="2025-01-15T12:00:00",
    )

    assert result["success"] is True
    assert result["time"] == "21:00:00"
    assert result["timezone"] == "Asia/Tokyo"


def test_spreadsheet_info_and_structured_extractors_succeed(sandboxWorkspace):
    source = sandboxWorkspace / "uploads" / "records.csv"
    source.write_text("name,value\nAda,42\n", encoding="utf-8")

    info = sheet("info", path="uploads/records.csv")
    xml = extract("xml", text="<record><name>Ada</name></record>")
    yaml = extract("yaml", text="name: Ada\ncount: 1\n")
    csv = extract("csv", text="name,value\nAda,42\n")

    assert info["success"] is True and info["rowCount"] == 1
    assert xml["success"] is True and xml["data"] == {"record": {"name": "Ada"}}
    assert yaml["success"] is True and yaml["data"] == {"name": "Ada", "count": 1}
    assert csv["success"] is True and csv["data"]["rows"] == [{"name": "Ada", "value": "42"}]


def test_audio_trim_and_convert_use_staged_ffmpeg_outputs(sandboxWorkspace, monkeypatch):
    source = sandboxWorkspace / "uploads" / "source.wav"
    source.write_bytes(b"source audio")
    monkeypatch.setattr("orchestrator.tools.definitions.audio.shutil.which", lambda _: "ffmpeg")

    def fakeRun(command, **kwargs):
        assert "-n" in command
        assert kwargs["timeout"] == 120
        from pathlib import Path

        Path(command[-1]).write_bytes(b"processed audio")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("orchestrator.tools.definitions.audio.subprocess.run", fakeRun)

    trimmed = audio(
        "trim", path="uploads/source.wav", output_path="outputs/clip.wav",
        start_seconds=1, duration_seconds=2,
    )
    converted = audio(
        "convert", path="uploads/source.wav", output_path="outputs/converted.mp3",
        output_format="mp3",
    )

    assert trimmed["success"] is True
    assert (sandboxWorkspace / "outputs" / "clip.wav").read_bytes() == b"processed audio"
    assert converted["success"] is True
    assert (sandboxWorkspace / "outputs" / "converted.mp3").read_bytes() == b"processed audio"


def test_image_generation_saves_provider_image(sandboxWorkspace):
    class ImageProvider:
        async def generate(self, prompt):
            assert prompt == "A blue square."
            return SimpleNamespace(images=[PillowImage.new("RGB", (2, 2), "blue")])

    result = asyncio.run(generateImage(
        "A blue square.", "outputs/generated.png", dispatcher=ImageProvider(),
    ))

    assert result["success"] is True
    with PillowImage.open(sandboxWorkspace / "outputs" / "generated.png") as generated:
        assert generated.size == (2, 2)
