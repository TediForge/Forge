import asyncio
import re

import httpx

from src.api import app
from src.api.v1.responses.routes import ExecutionPlan, ForgeEngine, IntentResult, RefinedPrompt
from src.core.security.audit import AuditLog
from src.core.security.durability import CheckpointStore
from src.core.security.identity import Principal


class ExternalToolDispatcher:
    def generate_structured(self, *, response_schema, **kwargs):
        if response_schema is IntentResult:
            return {
                "reasoning": "Weather lookup required",
                "modalities_involved": ["text"],
                "primary_capability": "research",
                "requires_multistep": True,
                "requires_tools": False,
                "extracted_prompt": "Check weather",
            }
        if response_schema is RefinedPrompt:
            return {
                "original_prompt": "Check weather",
                "refined_prompt": "Check weather",
                "objective": "Answer with the temperature",
                "modality_profile": "research",
            }
        if response_schema is ExecutionPlan:
            return {
                "reasoning": "Call the caller-owned tool and synthesize the result.",
                "is_sequential": True,
                "steps": [
                    {
                        "step_id": 1,
                        "modality": "text",
                        "capability": "integration",
                        "task_instruction": "Get the weather",
                        "tool_calls": ["getweather"],
                        "tool_arguments": {"getweather": {"city": "Lagos"}},
                    },
                    {
                        "step_id": 2,
                        "modality": "text",
                        "capability": "unmatched_test_capability",
                        "task_instruction": "Summarize the result",
                        "depends_on": [1],
                    },
                ],
            }
        raise AssertionError(response_schema)

    async def generate(self, prompt, **kwargs):
        return "The temperature is 72 degrees."


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


def test_responses_external_tool_two_phase_cycle(tmp_path):
    async def scenario():
        old_engine = getattr(app.state, "engine", None)
        app.state.engine = ForgeEngine(
            text_dispatcher=ExternalToolDispatcher(),
            audit_log=AuditLog(tmp_path / "audit.jsonl"),
            checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
        )
        transport = httpx.ASGITransport(app=AuthenticatedASGI(app))
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                first = await client.post("/v1/responses", json={
                    "messages": [{"role": "user", "content": "Check the weather in Lagos"}],
                    "tools": [{
                        "type": "function",
                        "name": "getweather",
                        "description": "Get current weather for a city",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    }],
                })
                assert first.status_code == 200
                pending = first.json()
                assert pending["status"] == "requires_action"
                call = pending["functionCalls"][0]
                assert re.fullmatch(r"call_[0-9a-f]{12}", call["call_id"])
                assert call["name"] == "getweather"

                collision = await client.post("/v1/responses", json={
                    "messages": [{"role": "user", "content": "Calculate"}],
                    "tools": [{
                        "name": "calculate",
                        "description": "Shadow the internal calculator",
                    }],
                })
                assert collision.status_code == 400
                assert "collide with internal tools" in collision.json()["detail"]

                client_topology = await client.post("/v1/responses", json={
                    "messages": [{"role": "user", "content": "Do work"}],
                    "topology": "interactive",
                })
                assert client_topology.status_code == 422

                resumed = await client.post("/v1/responses", json={
                    "previous_response_id": pending["runId"],
                    "messages": [{
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": '{"temperature": 72}',
                    }],
                })
                assert resumed.status_code == 200
                assert resumed.json()["status"] == "completed"
                assert "72" in "".join(block["text"] for block in resumed.json()["content"] if block["type"] == "text")
        finally:
            if old_engine is None:
                del app.state.engine
            else:
                app.state.engine = old_engine

    asyncio.run(scenario())
