from src.tools.definitions.extract import extract
from src.tools.definitions.summarize import summarize


def test_extract_returns_first_schema_matching_json_value():
    result = extract(
        "json",
        text='Status: {"ignored": true}; payload={"count": 4}',
        schema={"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]},
    )

    assert result == {
        "success": True,
        "data": {"count": 4},
        "source": '{"count": 4}',
        "error": None,
        "errorCode": None,
    }


def test_extract_reports_missing_json_and_schema_mismatch():
    schema = {"type": "object", "required": ["name"]}

    assert extract("json", text="There is no structured payload.", schema=schema)["errorCode"] == "NO_JSON"
    assert extract("json", text='{"age": 10}', schema=schema)["errorCode"] == "NO_MATCH"
    assert extract("json", text='{"name": "Ada"}', schema={"$ref": "https://example.test/schema.json"})["errorCode"] == "INVALID_SCHEMA"


def test_summarize_selects_source_sentences_in_order():
    result = summarize(
        "text",
        text="Oranges contain vitamin C. The train leaves at noon. Vitamin C supports normal immune function.",
        maxSentences=2,
    )

    assert result["success"] is True
    assert result["sentenceCount"] == 2
    assert result["method"] == "extractive"
    assert result["summary"] == "Oranges contain vitamin C. Vitamin C supports normal immune function."


def test_summarize_rejects_invalid_sentence_limit():
    assert summarize("text", text="A sentence.", maxSentences=0)["errorCode"] == "INVALID_LIMIT"
