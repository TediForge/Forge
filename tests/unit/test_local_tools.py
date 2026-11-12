import asyncio
import json
import sys
from types import SimpleNamespace

from orchestrator.tools.definitions.audio import TOOLS as audioTools
from orchestrator.tools.definitions.audio import audio
from orchestrator.tools.definitions.calculator import TOOLS as calculatorTools
from orchestrator.tools.definitions.calculator import calculate
from orchestrator.tools.definitions.clock import TOOLS as clockTools
from orchestrator.tools.definitions.clock import clock
from orchestrator.tools.definitions.image import generate as generateImage
from orchestrator.tools.definitions.search import search
from orchestrator.tools.definitions.spreadsheet import TOOLS as csvTools
from orchestrator.tools.definitions.spreadsheet import read, write


def test_calculator_returns_structured_numeric_result():
	result = calculate("evaluate", "sqrt(81) + 2 ** 3")

	assert result == {
		"success": True,
		"expression": "sqrt(81) + 2 ** 3",
		"result": 17.0,
		"error": None,
		"errorCode": None,
	}
	assert calculatorTools[0]["outputSchema"]["properties"]["result"]["type"] == ["number", "null"]
	assert "precise calculation" in calculatorTools[0]["function"]["description"]


def test_calculator_returns_agent_friendly_errors_and_enforces_bounds():
	assert calculate("evaluate", "1 / 0")["errorCode"] == "EVALUATION_ERROR"
	assert calculate("evaluate", "sqrt(-1)")["result"] is None
	assert calculate("evaluate", "open('secret')")["errorCode"] == "INVALID_EXPRESSION"
	assert calculate("evaluate", "2 ** 1001")["errorCode"] == "EVALUATION_ERROR"
	assert calculate("evaluate", "1" * 1001)["errorCode"] == "LENGTH_EXCEEDED"
	assert calculate("evaluate", "1e309")["errorCode"] == "EVALUATION_ERROR"


def test_search_returns_structured_results_and_bounded_page_evidence(monkeypatch):
	class FakeDDGS:
		def __enter__(self):
			return self

		def __exit__(self, *args):
			return False

		def text(self, query, max_results):
			assert query == "public data"
			assert max_results == 5
			return [{"title": "Docs", "href": "https://example.test/docs", "body": "Snippet"}]

		def extract(self, url, fmt):
			assert fmt == "text_markdown"
			return {"content": "Page evidence"}

	monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
	monkeypatch.setattr("orchestrator.tools.definitions.search._isPublicHttpsUrl", lambda _: True)

	result = search("web", query="public data", maxResults=5, extractResults=9)

	assert result["success"] is True
	assert result["results"][0] == {
		"title": "Docs", "url": "https://example.test/docs", "snippet": "Snippet", "content": "Page evidence",
	}


def test_search_returns_structured_rate_limit_error(monkeypatch):
	class RatelimitException(Exception):
		pass

	class FakeDDGS:
		def __enter__(self):
			return self

		def __exit__(self, *args):
			return False

		def text(self, query, max_results):
			raise RatelimitException

	monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))

	result = search("web", query="public data")

	assert result["success"] is False
	assert result["errorCode"] == "RATE_LIMITED"


def test_current_time_has_fixed_structured_contract():
	result = clock("now", "UTC")
	invalid = clock("now", "Not/A_Real_Zone")

	assert result["success"] is True
	assert {"iso", "date", "time", "weekday"}.issubset(result)
	assert invalid["success"] is False
	assert invalid["errorCode"] == "INVALID_TIMEZONE"
	assert "format" not in clockTools[0]["function"]["parameters"]["properties"]
	assert "outputSchema" in clockTools[0]


def test_csv_is_confined_bounded_and_formula_safe(sandboxWorkspace):
	writeResult = write(
		"outputs/exports/records.csv",
		["name", "value"],
		[["safe", 12], ["formula", "=1+1"], ["leading space", "  @SUM(A1:A2)"]],
	)
	readResult = read("outputs/exports/records.csv", maxRows=2)
	blocked = read("../outside.csv")

	assert writeResult["success"] is True
	assert readResult["success"] is True
	assert readResult["rowCount"] == 2
	assert readResult["rows"][1]["value"] == "'=1+1"
	assert blocked["success"] is False
	assert blocked["errorCode"] == "PATH_NOT_ALLOWED"
	assert csvTools[0]["outputSchema"]["properties"]["rowCount"]["type"] == "integer"
	assert "outputSchema" in csvTools[0]


def test_csv_returns_structured_errors_for_missing_files_and_delimiters(sandboxWorkspace):
	missing = read("missing.csv")
	badDelimiter = read("missing.csv", delimiter="||")

	assert missing["success"] is False
	assert missing["errorCode"] == "NOT_FOUND"
	assert badDelimiter["errorCode"] == "INVALID_DELIMITER"


def test_probe_audio_returns_trimmed_metadata_and_structured_errors(sandboxWorkspace, monkeypatch):
	audioFile = sandboxWorkspace / "uploads" / "sample.wav"
	audioFile.write_bytes(b"audio")
	metadata = {
		"format": {"duration": "3.5", "size": "100", "format_name": "wav", "bit_rate": "128000"},
		"streams": [
			{"codec_type": "audio", "codec_name": "pcm_s16le", "sample_rate": "44100", "channels": 2,
			 "channel_layout": "stereo", "bit_rate": "128000", "tags": {"irrelevant": "omit"}},
			{"codec_type": "video", "codec_name": "mjpeg"},
		],
	}
	monkeypatch.setattr("orchestrator.tools.definitions.audio.shutil.which", lambda _: "ffprobe")
	monkeypatch.setattr(
		"orchestrator.tools.definitions.audio.subprocess.run",
		lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(metadata), stderr=""),
	)

	result = audio("probe", str(audioFile))
	missing = audio("probe", "uploads/missing.wav")

	assert result["success"] is True
	assert result["durationSeconds"] == 3.5
	assert result["audioStreams"] == [{
		"codec": "pcm_s16le", "sampleRate": 44100, "channels": 2,
		"channelLayout": "stereo", "bitRate": 128000,
	}]
	assert "metadata" not in result
	assert missing["success"] is False and missing["errorCode"] == "NOT_FOUND"
	assert "outputSchema" in audioTools[0]


def test_image_generation_fails_explicitly_when_unconfigured():
	result = asyncio.run(generateImage("A landscape", "outputs/image.png"))

	assert result["success"] is False
	assert result["errorCode"] == "PROVIDER_NOT_CONFIGURED"