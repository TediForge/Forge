import asyncio
import json
import unittest
from types import SimpleNamespace
from fastapi import HTTPException

from src.agents import AgentRegistry, create_default_agents
from src.context.state import ExecutionState
from src.context.limits import ExecutionBudget, ExecutionLimits, ExecutionLimitError
from src.tools.registry import create_default_registry
from src.core.attachments import AttachmentDispatcherRouter
from src.api.v1.responses.routes import (
    ExecutionEvaluator,
    ExecutionPlan,
    ExecutionPlanner,
    ExecutionStep,
    ForgeEngine,
    IntentResult,
)
from src.core.schemas.input import AttachmentPayload, ExternalToolDefinition, ResponsesRequest
from src.core.security.identity import Principal
from src.core.security.rbac import Permission, authorize, require_authorization
from src.core.security.audit import AuditLog, redact
from src.core.security.durability import CheckpointStore
from src.synthesis.output import OutputSynthesizer
from src.core.schemas.output import TerminalStatus
from pydantic import ValidationError


INTENT = json.dumps({
    "reasoning": "Direct text request",
    "modalities_involved": ["text"],
    "primary_capability": "chat",
    "requires_multistep": False,
    "requires_tools": False,
    "extracted_prompt": "hello",
})


class ForgeProductionTests(unittest.TestCase):
    def test_structured_intent_and_static_engine(self):
        provider = SimpleNamespace(
            generate=lambda prompt=None, **kwargs: INTENT if "Analyze intent" in prompt else "answer"
        )
        provider.generate_text = provider.generate
        result = asyncio.run(ForgeEngine(text_dispatcher=provider).run(
            "hello", "session-1", user_id="user-1", tenant_id="tenant-a"
        ))
        self.assertEqual("".join(block.text or "" for block in result.content), "answer")
        self.assertEqual(result.metadata["status"], "completed")

    def test_agent_messages_and_scratchpad(self):
        async def run():
            state = ExecutionState("run-1")
            registry = AgentRegistry(create_default_agents(SimpleNamespace(
                generate=lambda prompt=None, **kwargs: "result"
            )))
            agent = registry.resolve("coding", "text")
            output = await registry.collaborate(agent, "Implement tests", state, 1)
            return output, state

        output, state = asyncio.run(run())
        self.assertEqual(output, "result")
        self.assertTrue(state.getAgentMessages())
        self.assertEqual(state.getScratchpad("coding.1.status"), "completed")

    def test_attachment_routing(self):
        attachment = AttachmentPayload(
            fileId="image-1", fileName="chart.png",
            fileData="AAAA", mimeType="image/png",
        )
        route = AttachmentDispatcherRouter.resolveToolForAttachment(attachment)
        self.assertTrue(route["supported"])
        self.assertEqual(route["targetDispatcher"], "vision")

    def test_tool_and_integration_intents_force_multi_step_plans(self):
        toolRegistry = create_default_registry()
        tool_intent = IntentResult(
            reasoning="Integration action required", modalities_involved=["text"],
            primary_capability="integration", requires_multistep=True,
            requires_tools=True, extracted_prompt="Create an issue from this report",
        )

        def generate_plan(**kwargs):
            self.assertIn("issue", kwargs["prompt"])
            return {
                "reasoning": "Prepare details, then suspend for the caller-owned issue tool.",
                "is_sequential": True,
                "steps": [
                    {"step_id": 1, "modality": "text", "capability": "research", "task_instruction": "Prepare issue details"},
                    {"step_id": 2, "modality": "text", "capability": "integration", "task_instruction": "Create the issue", "depends_on": [1], "tool_calls": ["issue"]},
                ],
            }

        planner = ExecutionPlanner(
            text_dispatcher=SimpleNamespace(generate_structured=generate_plan),
            toolRegistry=toolRegistry,
        )
        issueTool = ExternalToolDefinition(
            name="issue",
            description="Create an issue using the caller-owned issue service.",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
        )
        plan = planner.create_plan(tool_intent, external_tools=[issueTool])
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[1].depends_on, [1])
        self.assertEqual(plan.steps[1].tool_calls, ["issue"])

    def test_tool_plan_rejects_missing_planner_or_unregistered_names(self):
        toolRegistry = create_default_registry()
        tool_intent = IntentResult(
            reasoning="Tool required", modalities_involved=["text"],
            primary_capability="research", requires_tools=True,
            extracted_prompt="Search for this source",
        )
        with self.assertRaises(RuntimeError):
            ExecutionPlanner(toolRegistry=toolRegistry).create_plan(tool_intent)

        invalidPlanner = ExecutionPlanner(
            text_dispatcher=SimpleNamespace(generate_structured=lambda **kwargs: {
                "reasoning": "Invalid tool", "steps": [{
                    "step_id": 1, "modality": "text", "capability": "research",
                    "task_instruction": "Search", "tool_calls": ["not_registered"],
                }],
            }),
            toolRegistry=toolRegistry,
        )
        with self.assertRaisesRegex(ValueError, "unregistered tools"):
            invalidPlanner.create_plan(tool_intent)

    def test_execution_plan_is_ordered_by_dependencies(self):
        plan = ExecutionPlan(reasoning="DAG", steps=[
            ExecutionStep(step_id=1, modality="text", capability="research", task_instruction="Gather", depends_on=[]),
            ExecutionStep(step_id=2, modality="text", capability="coding", task_instruction="Implement", depends_on=[1]),
        ])
        ordered = ForgeEngine._orderedSteps(plan)
        self.assertEqual([step.step_id for step in ordered], [1, 2])

    def test_duplicate_action_raises_circuit_breaker(self):
        budget = ExecutionBudget(ExecutionLimits(max_steps=5))
        budget.begin_action("same-action", "first")
        with self.assertRaises(ExecutionLimitError) as caught:
            budget.begin_action("same-action", "duplicate")
        self.assertIn("Repeated action", str(caught.exception))

    def test_evaluator_stops_repeated_outputs(self):
        result = ExecutionEvaluator().evaluate("finish task", ["same result", "same result"])
        self.assertEqual(result.decision, "stop")

    def test_responses_request_schema(self):
        request = ResponsesRequest.model_validate({
            "model": "forge",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "Find an event"}]}],
            "previous_response_id": "resp-1",
            "max_output_tokens": 500,
        })
        dumped = request.model_dump(by_alias=True)
        self.assertEqual(request.previousResponseId, "resp-1")
        self.assertEqual(request.maxOutputTokens, 500)
        self.assertIn("previousResponseId", dumped)
        self.assertIn("maxOutputTokens", dumped)

    def test_tenant_and_rbac_isolation(self):
        viewer = Principal("user-1", "tenant-a", roles=("viewer",))
        operator = Principal("user-2", "tenant-a", roles=("operator",))
        self.assertTrue(authorize(viewer, Permission.READ_SESSION).allowed)
        self.assertFalse(authorize(viewer, Permission.RUN).allowed)
        self.assertTrue(authorize(operator, Permission.RUN).allowed)
        self.assertFalse(authorize(operator, Permission.RUN, "tenant-b").allowed)

    def test_audit_redacts_credentials(self):
        self.assertEqual(redact({"accessToken": "secret", "tool": "external_action"}), {"accessToken": "[REDACTED]", "tool": "external_action"})

    def test_tenant_scoped_checkpoint(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = CheckpointStore(directory)
            path = store.save("tenant-a", "run-1", "planned", {"ok": True})
            self.assertEqual(path.parent.name, "tenant-a")
            self.assertTrue(store.load("tenant-a", "run-1", "planned")["ok"])

    def test_synthesis_terminal_status_and_redaction(self):
        response = OutputSynthesizer.synthesizeStatic(
            "run-1", "Safe answer", reasoningLogs=[{
                "id": "T123AB", "message": "Called provider",
                "data": {"authorization": "Bearer secret"},
            }],
            metrics={"status": "success", "accessToken": "secret"}, status="completed",
        )
        self.assertEqual(response.metadata["status"], TerminalStatus.COMPLETED.value)
        self.assertEqual(response.events[0].data["authorization"], "[REDACTED]")
        self.assertEqual(response.metadata["accessToken"], "[REDACTED]")

    def test_stream_emits_ordered_complete_payload(self):
        async def events():
            yield {"type": "textChunk", "data": {"content": "answer"}}

        async def collect():
            return [event async for event in OutputSynthesizer.synthesizeStream(
                "run-stream", events(), status="completed"
            )]

        frames = asyncio.run(collect())
        self.assertIn("id: run-stream:1", frames[0])
        first_payload = json.loads(frames[0].split("data: ", 1)[1].strip())
        self.assertEqual(first_payload["sequence"], 1)
        self.assertIn("event: complete", frames[-1])
        complete_payload = json.loads(frames[-1].split("data: ", 1)[1].strip())
        self.assertEqual(complete_payload["data"]["metadata"]["status"], "completed")

    def test_synthesis_rejects_unknown_media_type(self):
        with self.assertRaises(ValidationError):
            OutputSynthesizer.synthesizeStatic("run-1", "answer", mediaAssets=[{"mediaType": "document", "url": "https://example.com/file.pdf"}])

    def test_request_schema(self):
        request = ResponsesRequest(
            model="forge", input=[{"role": "user", "content": "hello"}], stream=False
        )
        self.assertEqual(request.model, "forge")
        self.assertEqual(request.input[0].content, "hello")
        self.assertFalse(request.stream)

    def test_vision_and_media_agent_routing(self):
        registry = AgentRegistry(create_default_agents())
        self.assertEqual(registry.resolve("image_understanding", "vision").name, "vision")
        self.assertEqual(registry.resolve("video_generation", "image").name, "media")

    def test_data_agent_and_tools_registered(self):
        registry = AgentRegistry(create_default_agents())
        tools = create_default_registry()
        self.assertEqual(registry.resolve("data_analysis", "data").name, "data")
        self.assertIn("data", tools.names())
        self.assertFalse({"table", "sql", "profile", "join", "report", "chart"} & set(tools.names()))

    def test_sql_tool_rejects_writes(self):
        tools = create_default_registry()
        result = tools.execute("data", {
            "operation": "sql",
            "connection": "sqlite::memory:",
            "query": "DELETE FROM customers",
        })
        self.assertFalse(result["success"])
        self.assertIn(result["errorCode"], {"READ_ONLY_QUERY_REQUIRED", "NOT_FOUND"})

    def test_malformed_refiner_output_falls_back(self):
        provider = SimpleNamespace(
            generate=lambda prompt=None, **kwargs: (
                INTENT if "Analyze intent" in prompt else
                "plain text response" if "Prompt Refiner" in prompt else
                "answer"
            )
        )
        provider.generate_text = provider.generate
        result = asyncio.run(ForgeEngine(text_dispatcher=provider).run(
            "build api", "session-2", user_id="user-1", tenant_id="tenant-a"
        ))
        self.assertEqual("".join(block.text or "" for block in result.content), "answer")

    def test_consolidated_media_and_speech_tools_registered(self):
        tools = create_default_registry()
        registered = set(tools.names())
        self.assertTrue({"image", "video", "transcribe", "speak"}.issubset(registered))
        self.assertFalse({
            "info", "resize", "analyze", "ocr", "detect", "sample", "keyframe",
        } & registered)
        self.assertIn("generate", registered)


if __name__ == "__main__":
    unittest.main()
