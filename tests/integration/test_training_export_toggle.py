import asyncio
import json

import httpx

from src.api import app
from src.api.v1.responses.routes import ForgeEngine, IntentResult, RefinedPrompt
from src.core.security.audit import AuditLog
from src.core.security.durability import CheckpointStore
from src.core.security.identity import Principal


class DirectDispatcher:
    def generate_structured(self, *, response_schema, **kwargs):
        if response_schema is IntentResult:
            return {
                "reasoning": "Direct response",
                "modalities_involved": ["text"],
                "primary_capability": "unmatched_test_capability",
                "requires_multistep": False,
                "requires_tools": False,
                "extracted_prompt": "hello",
            }
        if response_schema is RefinedPrompt:
            return {
                "original_prompt": "hello",
                "refined_prompt": "hello",
                "objective": "Answer",
                "modality_profile": "text",
            }
        raise AssertionError(f"Unexpected planner call: {response_schema}")

    async def generate(self, prompt, **kwargs):
        return "hello from Forge"


class DirectChatProvider:
    def __init__(self):
        self.calls = []

    async def generateText(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return "hello from Forge"


class AuthenticatedASGI:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["principal"] = Principal(
                user_id="user-1",
                tenant_id="tenant-a",
                roles=("operator",),
            )
        await self.application(scope, receive, send)


def test_forge_chat_never_exports_and_responses_requires_opt_in(tmp_path, monkeypatch):
    export_dir = tmp_path / "training"
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_ENABLED", "true")
    monkeypatch.setenv("FORGE_TRAINING_EXPORT_DIR", str(export_dir))

    async def scenario():
        previous_engine = getattr(app.state, "engine", None)
        previous_chat_provider = getattr(app.state, "chatCompletionProvider", None)
        app.state.engine = ForgeEngine(
            text_dispatcher=DirectDispatcher(),
            audit_log=AuditLog(tmp_path / "audit.jsonl"),
            checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
        )
        chatProvider = DirectChatProvider()
        app.state.chatCompletionProvider = chatProvider
        transport = httpx.ASGITransport(app=AuthenticatedASGI(app))
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                chat = await client.post("/v1/chat/completions", json={
                    "model": "text",
                    "max_tokens": 64,
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "messages": [
                        {"role": "user", "content": "Plan a family trip to Nairobi"},
                        {"role": "assistant", "content": "I can help plan it."},
                        {"role": "user", "content": "hello"},
                    ],
                })
                assert chat.status_code == 200
                assert chat.json()["id"].startswith("chatcmpl_")
                assert isinstance(chat.json()["created"], int)
                assert chat.json()["model"] == "text"
                assert chat.json()["choices"][0]["message"]["content"] == "hello from Forge"
                assert "title" not in chat.json()
                assert chat.json()["object"] == "chat.completion"
                assert chat.json()["choices"][0]["finish_reason"] == "stop"
                assert chatProvider.calls[0][1] == {
                    "max_new_tokens": 64,
                    "temperature": 0.3,
                    "top_p": 0.8,
                }
                assert not list(export_dir.glob("*.jsonl"))

                chatStream = await client.post("/v1/chat/completions", json={
                    "model": "text",
                    "stream": True,
                    "max_completion_tokens": 18,
                    "top_p": 0.6,
                    "messages": [
                        {"role": "system", "content": "You are helpful."},
                        {"role": "user", "content": [{"type": "text", "text": "hello"}]},
                    ],
                })
                assert chatStream.status_code == 200
                streamChunks = [
                    json.loads(line[6:])
                    for line in chatStream.text.splitlines()
                    if line.startswith("data: {")
                ]
                streamedContent = "".join(
                    chunk["choices"][0]["delta"].get("content", "")
                    for chunk in streamChunks
                )
                assert streamedContent == "hello from Forge"
                assert "data: [DONE]" in chatStream.text
                assert chatProvider.calls[1][1] == {
                    "max_new_tokens": 18,
                    "temperature": 0.7,
                    "top_p": 0.6,
                }

                response = await client.post("/v1/responses", json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "metadata": {"trainingExport": True},
                })
                assert response.status_code == 200
                assert response.json()["content"] == [
                    {"type": "text", "text": "hello from Forge", "metadata": {}},
                ]
                await app.state.engine.trainingExporter.shutdown()
                lines = [json.loads(line) for path in export_dir.glob("*.jsonl") for line in path.read_text(encoding="utf-8").splitlines()]
                assert len(lines) == 1
                assert lines[0]["messages"] == [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hello from Forge"},
                ]
        finally:
            if previous_chat_provider is None:
                del app.state.chatCompletionProvider
            else:
                app.state.chatCompletionProvider = previous_chat_provider
            if previous_engine is None:
                del app.state.engine
            else:
                app.state.engine = previous_engine

    asyncio.run(scenario())


def test_model_catalog_and_embeddings_use_forge_models():
    class DirectEmbeddingProvider:
        async def embed(self, inputs):
            values = inputs if isinstance(inputs, list) else [inputs]
            return [[float(index), 0.5] for index, _ in enumerate(values)]

    async def scenario():
        previous_provider = getattr(app.state, "embeddingProvider", None)
        app.state.embeddingProvider = DirectEmbeddingProvider()
        transport = httpx.ASGITransport(app=AuthenticatedASGI(app))
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                models = await client.get("/v1/models")
                assert models.status_code == 200
                modelList = models.json()
                assert modelList["object"] == "list"
                modelsData = modelList["data"]
                assert {model["id"] for model in modelsData} == {
                    "text", "image", "audio", "transcription", "video", "vision", "document", "data", "embedding"
                }
                assert all(
                    set(model) == {"id", "object", "created", "owned_by"}
                    and
                    model["object"] == "model"
                    and isinstance(model["created"], int)
                    and model["owned_by"] == "tediforge"
                    for model in modelsData
                )
                textModel = await client.get("/v1/models/text")
                assert textModel.status_code == 200
                assert textModel.json() == {
                    "id": "text",
                    "object": "model",
                    "created": 0,
                    "owned_by": "tediforge",
                }

                embeddings = await client.post("/v1/embeddings", json={
                    "model": "embedding",
                    "input": ["hello", "Forge"],
                })
                assert embeddings.status_code == 200
                assert embeddings.json()["model"] == "embedding"
                assert embeddings.json()["data"] == [
                    {"object": "embedding", "index": 0, "embedding": [0.0, 0.5]},
                    {"object": "embedding", "index": 1, "embedding": [1.0, 0.5]},
                ]
        finally:
            if previous_provider is None:
                del app.state.embeddingProvider
            else:
                app.state.embeddingProvider = previous_provider

    asyncio.run(scenario())

