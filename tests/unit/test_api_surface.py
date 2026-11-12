from src.api import app


def test_versioned_routes_are_mounted_without_legacy_orchestrate_route():
    schema = app.openapi()
    paths = schema["paths"]
    assert "/v1/responses" in paths
    assert "/v1/chat/completions" in paths
    assert "/v1/models" in paths
    assert "/v1/embeddings" in paths
    assert "/v1/audio/transcriptions" in paths
    assert "/v1/audio/speech" in paths
    assert "/v1/titles" not in paths
    assert "/v1/orchestrate" not in paths

    modelResponse = schema["components"]["schemas"]["ModelResponse"]
    assert modelResponse["required"] == ["id", "object", "created", "owned_by"]
    assert modelResponse["properties"]["object"]["const"] == "model"

    modelListResponse = schema["components"]["schemas"]["ModelListResponse"]
    assert modelListResponse["required"] == ["object", "data"]
    assert modelListResponse["properties"]["object"]["const"] == "list"
