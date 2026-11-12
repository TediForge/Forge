"""
src/engine.py
Core orchestration engine for Forge Nano,
managing the end-to-end pipeline from user prompt to synthesized response.
"""
import asyncio
import inspect
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from dataclasses import replace
from hashlib import sha256
from functools import lru_cache
from typing import Callable, Dict, Any, Optional, AsyncGenerator, Literal, Union

from pydantic import BaseModel, Field, ValidationError
from opentelemetry import trace

from orchestrator.context.limits import ExecutionBudget, ExecutionLimits, ExecutionLimitError
from orchestrator.context.metrics import RuntimeMetrics
from orchestrator.context.runtime import RuntimeContext
from orchestrator.context.session import SessionManager
from orchestrator.context.state import ExecutionState
from orchestrator.synthesis.output import OutputSynthesizer, UnifiedOrchestratorResponse
from orchestrator.synthesis.normalizer import normalize_sources
from orchestrator.schemas.v1.responses import (
    AttachmentPayload,
    AttachmentType,
    CompleteStreamEvent,
    ExecutionTopology,
    ExternalToolDefinition,
    FollowUpSuggestion,
    FunctionCall,
    FunctionCallOutput,
)
from orchestrator.attachments import AttachmentDispatcherRouter
from orchestrator.media import MediaConversionError, MediaConverter
from orchestrator.agents import AgentRegistry, create_default_agents
from orchestrator.inference.modalities import CanvasDispatcher, SttDispatcher, TextDispatcher, VoiceDispatcher
from orchestrator.inference.gateway import InferenceGateway
from orchestrator.security.identity import IdentityContextError, Principal
from orchestrator.security.rbac import Permission, require_authorization
from orchestrator.security.audit import AuditLog
from orchestrator.security.durability import CheckpointStore
from orchestrator.skills.loader import loadSkillBody
from orchestrator.tools.executor import ToolExecutor, ToolResult
from orchestrator.sandbox.pathPolicy import cleanupTmp
from orchestrator.export.trajectory import TrajectoryExporter


logger = logging.getLogger(__name__)
tracer = trace.get_tracer("orchestrator.engine")


class RequestContractError(ValueError):
    """A caller-supplied request violates the orchestration contract."""


class SuspensionSignal(Exception):
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        super().__init__(f"External tool call requires caller action: {name}")
        self.call_id = call_id
        self.name = name
        self.arguments = arguments


@lru_cache(maxsize=None)
def _load_skill(name: str) -> str:
    return loadSkillBody(name, "general")


class IntentResult(BaseModel):
    reasoning: str
    modalities_involved: list[str]
    primary_capability: str
    requires_multistep: bool = False
    requires_tools: bool = False
    extracted_prompt: str


class IntentClassifier:
    def __init__(self, text_dispatcher=None):
        self.text_dispatcher = text_dispatcher

    def classify(self, prompt: str, attachments: Optional[list[str]] = None, context: str = "") -> IntentResult:
        attachment_context = f"\nAttached files: {', '.join(attachments)}" if attachments else ""
        request = f'User Request: "{prompt}"{attachment_context}\n{context}\n\nAnalyze intent and return structured classification.'
        skill = _load_skill("classifier")
        if self.text_dispatcher:
            structured = getattr(self.text_dispatcher, "generate_structured", None)
            if callable(structured):
                result = structured(system_prompt=skill, prompt=request, response_schema=IntentResult)
                if inspect.isawaitable(result):
                    raise RuntimeError("Synchronous intent analysis received an async dispatcher")
                return IntentResult.model_validate(result) if isinstance(result, dict) else result
            generator = getattr(self.text_dispatcher, "generate_text", None) or getattr(self.text_dispatcher, "generate", None)
            if callable(generator):
                raw = generator(prompt=f"{skill}\n\n{request}\nReturn only JSON.")
                if inspect.isawaitable(raw):
                    raise RuntimeError("Synchronous intent analysis received an async dispatcher")
                return self._parse_json(raw)
        return IntentResult(
            reasoning="Fallback intent analysis.", modalities_involved=["text"],
            primary_capability="chat", extracted_prompt=prompt.strip(),
        )

    async def classify_async(
        self,
        prompt: str,
        attachments: Optional[list[str]] = None,
        context: str = "",
    ) -> IntentResult:
        attachment_context = f"\nAttached files: {', '.join(attachments)}" if attachments else ""
        request = f'User Request: "{prompt}"{attachment_context}\n{context}\n\nAnalyze intent and return structured classification.'
        if self.text_dispatcher:
            skill = _load_skill("classifier")
            structured = getattr(self.text_dispatcher, "generate_structured", None)
            if callable(structured):
                result = structured(system_prompt=skill, prompt=request, response_schema=IntentResult)
                if inspect.isawaitable(result):
                    result = await result
                return IntentResult.model_validate(result) if isinstance(result, dict) else result
            generator = getattr(self.text_dispatcher, "generate_text", None) or getattr(self.text_dispatcher, "generate", None)
            if callable(generator):
                raw = generator(prompt=f"{skill}\n\n{request}\nReturn only JSON.")
                if inspect.isawaitable(raw):
                    raw = await raw
                return self._parse_json(raw)
        return IntentResult(
            reasoning="Fallback intent analysis.",
            modalities_involved=["text"],
            primary_capability="chat",
            extracted_prompt=prompt.strip(),
        )

    @staticmethod
    def _parse_json(raw: object) -> IntentResult:
        if hasattr(raw, "text"):
            raw = raw.text
        if isinstance(raw, dict):
            payload = raw
        elif isinstance(raw, str):
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("Intent dispatcher did not return valid JSON") from exc
        else:
            raise ValueError("Intent dispatcher returned an unsupported result")
        try:
            return IntentResult.model_validate(payload)
        except ValidationError as exc:
            raise ValueError("Intent dispatcher returned invalid intent data") from exc


class ExecutionStep(BaseModel):
    step_id: int
    modality: str
    capability: str
    task_instruction: str
    depends_on: Optional[list[int]] = None
    tool_calls: Optional[list[str]] = None
    tool_arguments: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    reasoning: str
    is_sequential: bool = False
    steps: list[ExecutionStep]


class _FollowUpBatch(BaseModel):
    suggestions: list[FollowUpSuggestion] = Field(default_factory=list, max_length=4)


class ExecutionPlanner:
    def __init__(self, text_dispatcher=None, toolRegistry=None):
        self.text_dispatcher = text_dispatcher
        if toolRegistry is None:
            from orchestrator.tools.registry import create_default_registry

            toolRegistry = create_default_registry()
        self.toolRegistry = toolRegistry

    def create_plan(
        self,
        intent: IntentResult,
        context: Optional[Dict[str, Any]] = None,
        external_tools: Optional[list[ExternalToolDefinition]] = None,
        reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium",
    ) -> ExecutionPlan:
        requiresPlanning = (
            intent.requires_multistep
            or intent.requires_tools
            or len(intent.modalities_involved) != 1
            or bool(external_tools)
        )
        if not requiresPlanning:
            return ExecutionPlan(
                reasoning="Direct single-step execution path.",
                steps=[ExecutionStep(
                    step_id=1, modality=intent.modalities_involved[0],
                    capability=intent.primary_capability, task_instruction=intent.extracted_prompt,
                )],
            )
        if self.text_dispatcher is None:
            raise RuntimeError("A planning model is required for tool or multi-step requests")

        availableTools = self.toolRegistry.definitions() + [
            {
                "type": "function",
                "function": tool.model_dump(exclude={"type"}, by_alias=True) | {"type": "function"},
            }
            for tool in external_tools or []
        ]
        request = (
            f"Intent Analysis:\n{intent.model_dump_json(indent=2)}\n\n"
            f"Execution effort: {reasoning_effort}. Keep the plan proportionate to this effort level.\n"
            f"Registered tool schemas:\n{json.dumps(availableTools, ensure_ascii=True)}\n\n"
            "Generate an ExecutionPlan using only these tool names. For each tool call, include its "
            "JSON arguments in the step's tool_arguments mapping keyed by tool name. Caller-supplied "
            "external tools are schemas only; selecting one pauses execution and returns control to "
            "the caller. Do not invent tools."
        )
        skill = _load_skill("planner")
        structured = getattr(self.text_dispatcher, "generate_structured", None)
        if callable(structured):
            result = structured(system_prompt=skill, prompt=request, response_schema=ExecutionPlan)
            if inspect.isawaitable(result):
                raise RuntimeError("Synchronous planning received an async structured dispatcher")
            plan = ExecutionPlan.model_validate(result) if isinstance(result, dict) else result
        else:
            generator = getattr(self.text_dispatcher, "generate_text", None) or getattr(self.text_dispatcher, "generate", None)
            if not callable(generator):
                raise RuntimeError("Planning dispatcher has no supported generation method")
            raw = generator(prompt=f"{skill}\n\n{request}\nReturn only JSON.")
            if inspect.isawaitable(raw):
                raise RuntimeError("Synchronous planning received an async dispatcher")
            plan = self._parse_plan(raw)
        return self._validatePlan(plan, intent, external_tools)

    async def create_plan_async(
        self,
        intent: IntentResult,
        context: Optional[Dict[str, Any]] = None,
        external_tools: Optional[list[ExternalToolDefinition]] = None,
        reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium",
    ) -> ExecutionPlan:
        requiresPlanning = (
            intent.requires_multistep
            or intent.requires_tools
            or len(intent.modalities_involved) != 1
            or bool(external_tools)
        )
        if not requiresPlanning:
            return self.create_plan(intent, context, external_tools, reasoning_effort)
        if self.text_dispatcher is None:
            raise RuntimeError("A planning model is required for tool or multi-step requests")
        availableTools = self.toolRegistry.definitions() + [
            {
                "type": "function",
                "function": tool.model_dump(exclude={"type"}, by_alias=True) | {"type": "function"},
            }
            for tool in external_tools or []
        ]
        request = (
            f"Intent Analysis:\n{intent.model_dump_json(indent=2)}\n\n"
            f"Execution effort: {reasoning_effort}. Keep the plan proportionate to this effort level.\n"
            f"Registered tool schemas:\n{json.dumps(availableTools, ensure_ascii=True)}\n\n"
            "Generate an ExecutionPlan using only these tool names. For each tool call, include its "
            "JSON arguments in the step's tool_arguments mapping keyed by tool name. Caller-supplied "
            "external tools are schemas only; selecting one pauses execution and returns control to "
            "the caller. Do not invent tools."
        )
        skill = _load_skill("planner")
        structured = getattr(self.text_dispatcher, "generate_structured", None)
        if callable(structured):
            result = structured(system_prompt=skill, prompt=request, response_schema=ExecutionPlan)
            if inspect.isawaitable(result):
                result = await result
            plan = ExecutionPlan.model_validate(result) if isinstance(result, dict) else result
        else:
            generator = getattr(self.text_dispatcher, "generate_text", None) or getattr(self.text_dispatcher, "generate", None)
            if not callable(generator):
                raise RuntimeError("Planning dispatcher has no supported generation method")
            raw = generator(prompt=f"{skill}\n\n{request}\nReturn only JSON.")
            if inspect.isawaitable(raw):
                raw = await raw
            plan = self._parse_plan(raw)
        return self._validatePlan(plan, intent, external_tools)

    def _validatePlan(
        self,
        plan: ExecutionPlan,
        intent: IntentResult,
        external_tools: Optional[list[ExternalToolDefinition]] = None,
    ) -> ExecutionPlan:
        registeredTools = set(self.toolRegistry.names()) | {tool.name for tool in external_tools or []}
        plannedTools = [toolName for step in plan.steps for toolName in (step.tool_calls or [])]
        unknownTools = sorted(set(plannedTools) - registeredTools)
        if unknownTools:
            raise ValueError(f"Plan references unregistered tools: {', '.join(unknownTools)}")
        if intent.requires_tools and not plannedTools:
            raise ValueError("Plan omitted tool calls for a request that requires tools")
        if not plan.steps:
            raise ValueError("Plan must contain at least one execution step")
        return plan

    @staticmethod
    def _parse_plan(raw: object) -> ExecutionPlan:
        if hasattr(raw, "text"):
            raw = raw.text
        if isinstance(raw, dict):
            payload = raw
        elif isinstance(raw, str):
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("Planner dispatcher did not return valid JSON") from exc
        else:
            raise ValueError("Planner dispatcher returned an unsupported result")
        try:
            return ExecutionPlan.model_validate(payload)
        except ValidationError as exc:
            raise ValueError("Planner dispatcher returned invalid plan data") from exc


class RefinedPrompt(BaseModel):
    original_prompt: str
    refined_prompt: str = Field(..., min_length=1)
    objective: str
    modality_profile: str
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)


class PromptRefiner:
    DOMAIN_PROFILES = {
        "text": "text generation and reasoning", "code": "software implementation and validation",
        "research": "source-grounded research and synthesis", "image": "image generation and visual art direction",
        "video": "video generation, composition, and editing", "vision": "image or video perception and evidence extraction",
        "document": "document extraction and structured analysis", "audio": "speech synthesis or audio processing",
        "data": "data analysis and structured reporting",
    }

    def __init__(self, text_dispatcher: Any = None) -> None:
        self.text_dispatcher = text_dispatcher

    def refine(
        self, prompt: str, intent: IntentResult, attachments: Optional[list[str]] = None,
        attachmentContents: Optional[list[dict[str, str]]] = None, historyBlock: str = "",
    ) -> RefinedPrompt:
        attachments = attachments or []
        profile = self._select_profile(intent)
        request = {
            "original_prompt": prompt, "intent": intent.model_dump(),
            "attachment_names": attachments, "attachmentContents": attachmentContents or [],
            "conversation_so_far": historyBlock, "domain_profile": profile,
        }
        skill = _load_skill("refiner")
        if self.text_dispatcher:
            structured = getattr(self.text_dispatcher, "generate_structured", None)
            if callable(structured):
                result = structured(system_prompt=skill, prompt=json.dumps(request), response_schema=RefinedPrompt)
                if inspect.isawaitable(result):
                    raise RuntimeError("Synchronous refinement received an async dispatcher")
                return RefinedPrompt.model_validate(result) if isinstance(result, dict) else result
            generator = getattr(self.text_dispatcher, "generate_text", None) or getattr(self.text_dispatcher, "generate", None)
            if callable(generator):
                raw = generator(prompt=f"{skill}\n\n{json.dumps(request)}\nReturn only JSON.")
                if inspect.isawaitable(raw):
                    raise RuntimeError("Synchronous refinement received an async dispatcher")
                return self._parse_result(raw, prompt)
        return self._deterministic_fallback(prompt, intent, profile)

    async def refine_async(
        self,
        prompt: str,
        intent: IntentResult,
        attachments: Optional[list[str]] = None,
        attachmentContents: Optional[list[dict[str, str]]] = None,
        historyBlock: str = "",
    ) -> RefinedPrompt:
        attachments = attachments or []
        profile = self._select_profile(intent)
        request = {
            "original_prompt": prompt,
            "intent": intent.model_dump(),
            "attachment_names": attachments,
            "attachmentContents": attachmentContents or [],
            "conversation_so_far": historyBlock,
            "domain_profile": profile,
        }
        if self.text_dispatcher:
            skill = _load_skill("refiner")
            structured = getattr(self.text_dispatcher, "generate_structured", None)
            if callable(structured):
                result = structured(system_prompt=skill, prompt=json.dumps(request), response_schema=RefinedPrompt)
                if inspect.isawaitable(result):
                    result = await result
                return RefinedPrompt.model_validate(result) if isinstance(result, dict) else result
            generator = getattr(self.text_dispatcher, "generate_text", None) or getattr(self.text_dispatcher, "generate", None)
            if callable(generator):
                raw = generator(prompt=f"{skill}\n\n{json.dumps(request)}\nReturn only JSON.")
                if inspect.isawaitable(raw):
                    raw = await raw
                return self._parse_result(raw, prompt)
        return self._deterministic_fallback(prompt, intent, profile)

    def _select_profile(self, intent: IntentResult) -> str:
        capability = intent.primary_capability.lower().replace("_", " ")
        modalities = {item.lower() for item in intent.modalities_involved}
        if "code" in capability or "coding" in capability:
            return self.DOMAIN_PROFILES["code"]
        if "research" in capability or intent.requires_tools:
            return self.DOMAIN_PROFILES["research"]
        for key in ("image", "video", "vision", "document", "audio", "data"):
            if key in capability or key in modalities:
                return self.DOMAIN_PROFILES[key]
        return self.DOMAIN_PROFILES["text"]

    def _deterministic_fallback(self, prompt: str, intent: IntentResult, profile: str) -> RefinedPrompt:
        return RefinedPrompt(
            original_prompt=prompt,
            refined_prompt=(f"{prompt.strip()}\n\nDomain profile: {profile}. Produce a complete, specific result. "
                           "State assumptions explicitly, apply constraints, validate the result, and prioritize accuracy."),
            objective=intent.extracted_prompt.strip(), modality_profile=profile,
            constraints=["Preserve the user's original intent", "Do not invent unavailable facts"],
            acceptance_criteria=["The response directly satisfies the requested objective"],
        )

    @staticmethod
    def _parse_result(raw: object, original_prompt: str) -> RefinedPrompt:
        if hasattr(raw, "text"):
            raw = raw.text
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(payload, dict):
                raise ValueError
            payload.setdefault("original_prompt", original_prompt)
            return RefinedPrompt.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
            return RefinedPrompt(
                original_prompt=original_prompt,
                refined_prompt=(f"{original_prompt.strip()}\n\nProvide a complete, specific result while preserving intent, "
                               "stating relevant assumptions, and validating the result."),
                objective=original_prompt.strip(), modality_profile="general task",
                constraints=["Preserve the user's original intent"],
                acceptance_criteria=["The response directly satisfies the requested objective"],
                ambiguity_flags=["The provider returned non-structured refinement output"],
            )


class EvaluationResult(BaseModel):
    decision: str = Field(..., pattern="^(continue|summarize|stop)$")
    progress_score: float = Field(..., ge=0.0, le=1.0)
    reasoning: str


class ExecutionEvaluator:
    def __init__(self, text_dispatcher=None, stall_limit: int = 2) -> None:
        self.text_dispatcher = text_dispatcher
        self.stall_limit = stall_limit

    def evaluate(self, objective: str, output_history: list[Any], previous_scores: list[float] | None = None) -> EvaluationResult:
        return self._evaluateDeterministically(objective, output_history, previous_scores)

    async def evaluate_async(
        self,
        objective: str,
        output_history: list[Any],
        previous_scores: list[float] | None = None,
    ) -> EvaluationResult:
        previous_scores = previous_scores or []
        if self.text_dispatcher and output_history:
            structured = getattr(self.text_dispatcher, "generate_structured", None)
            if callable(structured):
                request = json.dumps({
                    "objective": objective,
                    "output_history": output_history[-self.stall_limit - 1:],
                    "previous_scores": previous_scores[-self.stall_limit:],
                }, ensure_ascii=True, default=str)
                result = structured(
                    system_prompt=_load_skill("evaluator"),
                    prompt=request,
                    response_schema=EvaluationResult,
                )
                if inspect.isawaitable(result):
                    result = await result
                return EvaluationResult.model_validate(result)
        return self._evaluateDeterministically(objective, output_history, previous_scores)

    def _evaluateDeterministically(
        self,
        objective: str,
        output_history: list[Any],
        previous_scores: list[float] | None = None,
    ) -> EvaluationResult:
        previous_scores = previous_scores or []
        if len(output_history) < 2:
            return EvaluationResult(decision="continue", progress_score=0.5, reasoning="Insufficient history to assess progress.")
        fingerprints = [sha256(str(item).strip().lower().encode("utf-8", errors="replace")).hexdigest()
                        for item in output_history[-self.stall_limit - 1:]]
        if len(set(fingerprints)) == 1:
            return EvaluationResult(decision="stop", progress_score=0.0, reasoning="Repeated identical outputs indicate no progress.")
        if len(previous_scores) >= self.stall_limit:
            recent = previous_scores[-self.stall_limit:]
            if max(recent) - min(recent) < 0.05:
                return EvaluationResult(decision="summarize", progress_score=max(recent), reasoning="Progress has plateaued across recent iterations.")
        score = 0.75 if fingerprints[-1] != fingerprints[-2] else 0.25
        return EvaluationResult(decision="continue", progress_score=score, reasoning=f"Execution output changed while working toward: {objective}")


class ForgeEngine:
    """
    Main orchestrator engine that coordinates intent analysis, execution planning,
    dispatcher invocation, and output synthesis.
    """

    def __init__(self, text_dispatcher=None, dispatcher_registry=None, execution_limits: ExecutionLimits | None = None,
                 audit_log: AuditLog | None = None, checkpoint_store: CheckpointStore | None = None,
                 metrics: RuntimeMetrics | None = None,
                 input_policy: Callable[[str, Principal], None] | None = None,
                 output_policy: Callable[[str, Principal], str] | None = None,
                 inference_gateway: InferenceGateway | None = None):
        self.textDispatcher = text_dispatcher
        self.inferenceGateway = inference_gateway or InferenceGateway()
        self._ownsInferenceGateway = inference_gateway is None
        self.executionLimits = execution_limits or ExecutionLimits()
        self.auditLog = audit_log or AuditLog()
        self.checkpointStore = checkpoint_store or CheckpointStore()
        self.metrics = metrics
        self.inputPolicy = input_policy or self._validateInput
        self.outputPolicy = output_policy or self._validateOutput
        self.trajectoryExporter = TrajectoryExporter.from_environment()
        configured_dispatchers = dict(dispatcher_registry or {})
        self._ownedDispatchers = []
        if "text" not in configured_dispatchers:
            configured_dispatchers["text"] = self.textDispatcher or TextDispatcher(self.inferenceGateway.get("text"))
        if "image" not in configured_dispatchers:
            configured_dispatchers["image"] = CanvasDispatcher(self.inferenceGateway.get("image"))
            self._ownedDispatchers.append(configured_dispatchers["image"])
        if "audio" not in configured_dispatchers:
            configured_dispatchers["audio"] = VoiceDispatcher(self.inferenceGateway.get("audio"))
            self._ownedDispatchers.append(configured_dispatchers["audio"])
        if "stt" not in configured_dispatchers:
            configured_dispatchers["stt"] = SttDispatcher(self.inferenceGateway.get("transcription"))
            self._ownedDispatchers.append(configured_dispatchers["stt"])
        self.dispatcherRegistry = configured_dispatchers
        self._closed = False
        self.agentRegistry = AgentRegistry(create_default_agents(
            self.textDispatcher,
            vision_dispatcher=configured_dispatchers.get("vision"),
        ))
        self.mediaConverter = MediaConverter.from_environment()
        self.toolExecutor = ToolExecutor(
            mediaConverter=self.mediaConverter,
            toolDependencies={
                "fetch": {"mediaConverter": self.mediaConverter},
                "image": {"dispatcher": configured_dispatchers["image"]},
                "generate": {
                    "imageDispatcher": configured_dispatchers["image"],
                    "audioDispatcher": configured_dispatchers["audio"],
                },
                "summarize": {"mediaConverter": self.mediaConverter},
                "translate": {"dispatcher": configured_dispatchers["text"]},
                "speak": {"dispatcher": configured_dispatchers["audio"]},
                "transcribe": {"dispatcher": configured_dispatchers["stt"]},
            },
        )
        self.toolRegistry = self.toolExecutor.registry
        
        # Initialize core reasoning modules
        self.intentClassifier = IntentClassifier(text_dispatcher=self.textDispatcher)
        self.executionPlanner = ExecutionPlanner(text_dispatcher=self.textDispatcher, toolRegistry=self.toolRegistry)
        self.promptRefiner = PromptRefiner(text_dispatcher=self.textDispatcher)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        closers = []
        for dispatcher in self._ownedDispatchers:
            close = getattr(dispatcher, "close", None)
            if callable(close):
                result = close()
                if inspect.isawaitable(result):
                    closers.append(result)
        closers.extend((self.trajectoryExporter.shutdown(), self.mediaConverter.close()))
        if self._ownsInferenceGateway:
            closers.append(self.inferenceGateway.close())
        results = await asyncio.gather(*closers, return_exceptions=True)
        errors = [result for result in results if isinstance(result, BaseException)]
        if errors:
            raise ExceptionGroup("One or more engine resources failed to close", errors)

    async def run(
        self,
        prompt: str,
        sessionId: str | None = None,
        stream: bool = False,
        attachments: Optional[list] = None,
        history: Optional[list] = None,
        toolArguments: Optional[Dict[str, Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        principal: Optional[Principal] = None,
        external_tools: Optional[list[ExternalToolDefinition | dict[str, Any]]] = None,
        reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium",
        trajectory_export: bool = False,
        include_suggestions: bool = False,
    ) -> Union[UnifiedOrchestratorResponse, AsyncGenerator[str, None]]:
        """
        Executes a complete orchestrator run given a user prompt and session parameters.
        """
        if external_tools is not None:
            external_tools = [
                tool if isinstance(tool, ExternalToolDefinition) else ExternalToolDefinition.model_validate(tool)
                for tool in external_tools
            ]
        internal_names = set(self.toolRegistry.names())
        collisions = sorted(internal_names.intersection(tool.name for tool in external_tools or []))
        if collisions:
            raise RequestContractError(f"External tool names collide with internal tools: {', '.join(collisions)}")
        topology = (
            ExecutionTopology.INTERACTIVE if external_tools
            else ExecutionTopology.AUTONOMOUS
        )
        if reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            raise RequestContractError("reasoning_effort must be low, medium, high, or xhigh.")
        if trajectory_export and not self.trajectoryExporter.enabled:
            raise RequestContractError("trajectoryExport requested but trajectory export is disabled server-side.")
        if trajectory_export and topology == ExecutionTopology.INTERACTIVE:
            raise RequestContractError(
                "trajectoryExport is not supported for interactive runs; exports require a complete prompt/response run."
            )

        runId = f"run_{uuid.uuid4().hex[:8]}"
        attachments = attachments or []
        budget = ExecutionBudget(self.executionLimits)
        if principal is None:
            if not user_id or not tenant_id:
                raise IdentityContextError("Authenticated user and tenant identity are required")
            principal = Principal(user_id=user_id, tenant_id=tenant_id, roles=("operator",))
        require_authorization(principal, Permission.RUN)

        attachments = [
            rawFile if isinstance(rawFile, AttachmentPayload) else AttachmentPayload.model_validate(rawFile)
            for rawFile in attachments
        ]

        try:
            removedTmpFiles = cleanupTmp()
            if removedTmpFiles:
                self.auditLog.record(
                    "sandbox.tmp.cleaned", runId, principal.tenant_id, principal.user_id,
                    filesRemoved=removedTmpFiles,
                )
        except Exception as exc:
            try:
                self.auditLog.record(
                    "sandbox.tmp.cleanup_failed", runId, principal.tenant_id, principal.user_id,
                    errorType=type(exc).__name__,
                )
            except Exception:
                pass

        # 1. Initialize context and state containers
        ambientContext = RuntimeContext.getAmbientContext()
        sessionId = sessionId or f"session_{uuid.uuid4().hex[:8]}"
        sessionManager = SessionManager(sessionId=sessionId, history=history)
        historyBlock = sessionManager.prompt_block(max_chars=8000)
        priorHistory = sessionManager.recent(10)
        executionState = ExecutionState(runId=runId, initialPayload={
            "ambient": ambientContext,
            "userId": principal.user_id,
            "tenantId": principal.tenant_id,
            "principalRoles": principal.roles,
            "toolArguments": toolArguments or {},
            "topology": topology.value,
            "externalTools": [tool.model_dump(mode="json") for tool in external_tools or []],
            "externalToolNames": [tool.name for tool in external_tools or []],
            "completedToolCalls": {},
            "completedStepIds": [],
            "evaluationScores": [],
            "resumeCache": {},
            "trajectoryExport": trajectory_export,
            "reasoningEffort": reasoning_effort,
            "sessionId": sessionId,
            "sessionHistory": priorHistory,
            "startedMonotonic": time.monotonic(),
        })
        try:
            with tracer.start_as_current_span("orchestrator.policy.input"):
                self.inputPolicy(prompt, principal)
        except asyncio.CancelledError:
            self._recordTerminal(executionState, "cancelled", "request_cancelled")
            raise
        except Exception as exc:
            self._recordTerminal(
                executionState,
                "failed",
                type(exc).__name__,
                errorType=type(exc).__name__,
                stage="input_policy",
            )
            raise

        # 1.1 Process any incoming attachments through the attachment router
        parsedAttachments: list[AttachmentPayload] = []
        attachmentContents: list[dict[str, str]] = []
        inlineAttachments: list[dict[str, str]] = []
        attachmentContextLength = 0
        for rawFile in attachments:
            if isinstance(rawFile, dict):
                attachmentObj = AttachmentPayload.model_validate(rawFile)
            else:
                attachmentObj = rawFile
            if not isinstance(attachmentObj, AttachmentPayload):
                raise RequestContractError("attachments must use the base64 AttachmentPayload contract.")
            parsedAttachments.append(attachmentObj)
            if attachmentObj.fileData is not None:
                inlineAttachments.append({
                    "fileId": attachmentObj.fileId,
                    "fileName": attachmentObj.fileName,
                    "mimeType": attachmentObj.mimeType,
                    "mediaData": attachmentObj.fileData,
                })
            routingDecision = AttachmentDispatcherRouter.resolveToolForAttachment(attachmentObj)
            executionState.setVariable(f"attachment_{attachmentObj.fileId}", routingDecision)
            extracted = AttachmentDispatcherRouter.extract_content(attachmentObj)
            if not extracted.supported:
                logger.warning("Attachment %s was not extracted: %s", attachmentObj.fileId, extracted.reason)
                continue
            remaining = max(0, 12000 - attachmentContextLength)
            text = extracted.content[:min(4000, remaining)]
            if text:
                attachmentContents.append({
                    "fileId": attachmentObj.fileId,
                    "fileName": attachmentObj.fileName,
                    "content": text,
                })
                attachmentContextLength += len(text)

        # Record the current turn after taking the preceding history snapshot.
        sessionManager.addMessage("user", prompt)
        executionState.setVariable("attachmentContents", attachmentContents)
        executionState.setVariable("inlineAttachments", inlineAttachments)

        # 2. Classify intent
        try:
            with tracer.start_as_current_span("orchestrator.classify"):
                intentResult: IntentResult = await self.intentClassifier.classify_async(
                    prompt=prompt,
                    attachments=[att.fileName for att in parsedAttachments],
                    context=self._attachmentPromptBlock(attachmentContents, historyBlock),
                )
        except asyncio.CancelledError:
            self._recordTerminal(executionState, "cancelled", "request_cancelled", stage="classify")
            raise
        except Exception as exc:
            self._recordTerminal(
                executionState,
                "failed",
                type(exc).__name__,
                errorType=type(exc).__name__,
                stage="classify",
            )
            raise
        if any(item.attachmentType == AttachmentType.IMAGE for item in parsedAttachments):
            intentResult.modalities_involved = ["vision"]
            intentResult.primary_capability = "visionInspection"
        executionState.setVariable("intentResult", intentResult.model_dump())

        # 3. Refine the request before execution planning.
        try:
            with tracer.start_as_current_span("orchestrator.refine"):
                refinedPrompt = await self.promptRefiner.refine_async(prompt, intentResult, [
                    att.fileName for att in parsedAttachments
                ], attachmentContents=attachmentContents, historyBlock=historyBlock)
        except asyncio.CancelledError:
            self._recordTerminal(executionState, "cancelled", "request_cancelled", stage="refine")
            raise
        except Exception as exc:
            self._recordTerminal(
                executionState,
                "failed",
                type(exc).__name__,
                errorType=type(exc).__name__,
                stage="refine",
            )
            raise
        executionState.setVariable("originalPrompt", prompt)
        intentResult.extracted_prompt = refinedPrompt.refined_prompt

        # 4. Create execution plan graph
        try:
            with tracer.start_as_current_span("orchestrator.plan"):
                executionPlan: ExecutionPlan = await self.executionPlanner.create_plan_async(
                    intent=intentResult.model_copy(update={"extracted_prompt": prompt}),
                    context=executionState.exportState(),
                    external_tools=external_tools,
                    reasoning_effort=reasoning_effort,
                )
        except asyncio.CancelledError:
            self._recordTerminal(executionState, "cancelled", "request_cancelled", stage="plan")
            raise
        except Exception as exc:
            self._recordTerminal(
                executionState,
                "failed",
                type(exc).__name__,
                errorType=type(exc).__name__,
                stage="plan",
            )
            raise
        executionState.setVariable("executionPlan", executionPlan.model_dump())
        self.checkpointStore.save(principal.tenant_id, runId, "planned", executionState.exportState())
        self.auditLog.record("run.planned", runId, principal.tenant_id, principal.user_id, steps=len(executionPlan.steps))

        # 4. Handle execution based on stream preference
        if stream:
            execution = OutputSynthesizer.synthesizeStream(
                runId=runId,
                executionGenerator=self._executeGraphStreamWithCancellation(
                    executionPlan, executionState, budget,
                )
            )
            if trajectory_export:
                if include_suggestions:
                    execution = self._streamWithSuggestions(execution)
                return self._recordStreamingTrajectoryExport(execution, prompt, executionState)
            if include_suggestions:
                return self._streamWithSuggestions(execution)
            return execution
        else:
            try:
                finalText, reasoningLogs, sources, contentBlocks, actions = await self._executeGraphStatic(
                    executionPlan,
                    executionState,
                    budget,
                )
                finalText = self.outputPolicy(finalText, principal)
                contentBlocks = self._applyOutputPolicy(contentBlocks, finalText)
            except SuspensionSignal as signal:
                self._recordTerminal(
                    executionState,
                    "requires_action",
                    "external_tool",
                    callId=signal.call_id,
                    toolName=signal.name,
                )
                function_call = FunctionCall(
                    call_id=signal.call_id,
                    name=signal.name,
                    arguments=signal.arguments,
                )
                return OutputSynthesizer.synthesizeStatic(
                    runId=runId,
                    content="",
                    reasoningLogs=executionState.getVariable("reasoningLogs", []),
                    actions=executionState.getVariable("actions", []),
                    status="requires_action",
                    responseStatus="requires_action",
                    functionCalls=[function_call],
                    events=executionState.getVariable("events", []),
                )
            except asyncio.CancelledError:
                self._recordTerminal(executionState, "cancelled", "request_cancelled")
                raise
            except Exception as exc:
                self._recordTerminal(
                    executionState,
                    "failed",
                    type(exc).__name__,
                    errorType=type(exc).__name__,
                )
                raise
            
            # Record assistant response
            sessionManager.addMessage("assistant", finalText)

            terminalStatus = "failed" if budget.terminal_status == "failed" else "completed"
            self._recordTerminal(
                executionState,
                terminalStatus,
                budget.termination_reason,
                stepsExecuted=budget.steps,
                toolCallCount=budget.tool_calls,
            )
            response = OutputSynthesizer.synthesizeStatic(
                runId=runId,
                content=contentBlocks,
                reasoningLogs=reasoningLogs,
                actions=actions,
                sources=sources,
                status=budget.terminal_status,
                metrics={"stepsExecuted": budget.steps, "terminationReason": budget.termination_reason, **budget.metrics()},
                events=executionState.getVariable("events", []),
                failures=executionState.getVariable("failures", []),
                terminationReason=budget.termination_reason,
            )
            if include_suggestions and response.status == "completed" and response.content:
                response.suggestions = await self._generateFollowUpSuggestions(response)
            if trajectory_export and response.metadata.get("status") == "completed":
                self.trajectoryExporter.record(
                    prompt=prompt,
                    final_response="".join(block.text or "" for block in response.content if block.type == "text"),
                    metadata={
                        "run_id": runId,
                        "reasoning_effort": reasoning_effort,
                        "topology": topology.value,
                    },
                    steps=[
                        event for event in executionState.getVariable("events", [])
                        if isinstance(event, dict) and event.get("type") == "status"
                    ],
                    tool_calls=executionState.getVariable("actions", []),
                    outcome={"status": response.status, "terminationReason": response.metadata.get("terminationReason")},
                )
            return response

    async def _generateFollowUpSuggestions(
        self,
        response: UnifiedOrchestratorResponse,
    ) -> list[FollowUpSuggestion]:
        generator = getattr(self.textDispatcher, "generate_structured", None)
        if not callable(generator):
            return []
        answer = "".join(block.text or "" for block in response.content if block.type == "text")
        if not answer:
            return []
        prompt = (
            "Suggest 2 to 4 short next messages the user could send, based only on the answer below. "
            "Write each prompt in the user's voice as a direct question or command, never as an assistant offer. "
            "Return an object with a suggestions array; each item has required prompt and optional title.\n\n"
            f"Answer:\n{answer}"
        )
        try:
            result = generator(
                system_prompt="Generate concise, relevant follow-up user prompts.",
                prompt=prompt,
                response_schema=_FollowUpBatch,
            )
            if inspect.isawaitable(result):
                result = await result
            batch = _FollowUpBatch.model_validate(result)
            if not 2 <= len(batch.suggestions) <= 4:
                return []
            return batch.suggestions
        except Exception:
            logger.warning("Follow-up suggestion generation failed for run %s", response.runId, exc_info=True)
            return []

    async def _streamWithSuggestions(
        self,
        execution: AsyncGenerator[str, None],
    ) -> AsyncGenerator[str, None]:
        async for frame in execution:
            if not frame.startswith("event: complete\n"):
                yield frame
                continue
            try:
                encoded = frame.split("data: ", 1)[1].strip()
                packet = CompleteStreamEvent.model_validate_json(encoded)
                response = packet.data
                if response.status == "completed" and response.content:
                    response.suggestions = await self._generateFollowUpSuggestions(response)
                yield (
                    "event: complete\n"
                    f"id: {packet.runId}:{packet.sequence}\n"
                    f"data: {packet.model_copy(update={'data': response}).model_dump_json(by_alias=True, exclude_none=True)}\n\n"
                )
            except (IndexError, ValidationError, ValueError):
                logger.exception("Could not add suggestions to completion stream event")
                yield frame

    async def _recordStreamingTrajectoryExport(
        self,
        execution: AsyncGenerator[str, None],
        prompt: str,
        state: ExecutionState,
    ) -> AsyncGenerator[str, None]:
        async for frame in execution:
            yield frame
            if not frame.startswith("event: complete\n"):
                continue
            try:
                packet = json.loads(frame.split("data: ", 1)[1].strip())
                response = packet.get("data", {})
                if response.get("status") == "completed" and response.get("metadata", {}).get("status") == "completed":
                    self.trajectoryExporter.record(
                        prompt=prompt,
                        final_response="".join(
                            str(block.get("text", ""))
                            for block in response.get("content", [])
                            if isinstance(block, dict) and block.get("type") == "text"
                        ),
                        metadata={
                            "run_id": state.runId,
                            "reasoning_effort": state.getVariable("reasoningEffort"),
                        },
                        steps=[
                            event for event in response.get("events", [])
                            if isinstance(event, dict) and event.get("type") == "status"
                        ],
                        tool_calls=[
                            event for event in response.get("events", [])
                            if isinstance(event, dict) and event.get("type") == "action"
                        ],
                        outcome={"status": response.get("status", "completed")},
                    )
            except Exception:
                logger.exception("Could not export completed streaming response")
            return

    async def resume(
        self,
        run_id: str,
        function_call_outputs: list[FunctionCallOutput | dict[str, Any]],
        user_id: str | None = None,
        tenant_id: str | None = None,
        principal: Principal | None = None,
        include_suggestions: bool = False,
    ) -> UnifiedOrchestratorResponse:
        if principal is None:
            if not user_id or not tenant_id:
                raise IdentityContextError("Authenticated user and tenant identity are required")
            principal = Principal(user_id=user_id, tenant_id=tenant_id, roles=("operator",))
        require_authorization(principal, Permission.RUN)
        outputs = [
            item if isinstance(item, FunctionCallOutput) else FunctionCallOutput.model_validate(item)
            for item in function_call_outputs
        ]
        if len(outputs) != 1:
            raise RequestContractError("A resume request must contain exactly one function_call_output.")
        checkpoint = self.checkpointStore.load(principal.tenant_id, run_id, "suspended")
        if checkpoint is None:
            raise RequestContractError(f"No suspended run: {run_id}")
        state = ExecutionState.fromExport(checkpoint)
        state.setVariable("startedMonotonic", time.monotonic())
        if isinstance(checkpoint.get("variables"), dict):
            state.setVariable("sessionHistory", checkpoint["variables"].get("sessionHistory", []))
        if state.getVariable("userId") != principal.user_id:
            raise RequestContractError("Suspended run does not belong to this user.")
        output = outputs[0]
        resume_cache = state.getVariable("resumeCache", {})
        cached = resume_cache.get(output.call_id)
        if cached is not None:
            response = UnifiedOrchestratorResponse.model_validate(cached)
            if include_suggestions and response.status == "completed" and response.content and not response.suggestions:
                response.suggestions = await self._generateFollowUpSuggestions(response)
                resume_cache[output.call_id] = response.model_dump(by_alias=True, exclude_none=True)
                state.setVariable("resumeCache", resume_cache)
                self.checkpointStore.save(principal.tenant_id, run_id, "suspended", state.exportState())
            return response
        if checkpoint.get("status") != "suspended":
            raise RequestContractError(f"No suspended run: {run_id}")
        if output.call_id != checkpoint.get("pendingCallId"):
            raise RequestContractError("function_call_output call_id does not match the pending call.")

        pending_name = str(checkpoint["pendingToolName"])
        pending_step_id = int(checkpoint["pendingStepId"])
        self.auditLog.record(
            "run.resumed",
            run_id,
            principal.tenant_id,
            principal.user_id,
            callId=output.call_id,
            toolName=pending_name,
        )
        result: dict[str, Any] = {"success": True, "data": output.output}
        tool_key = f"{pending_step_id}:{pending_name}"
        completed_tools = state.getVariable("completedToolCalls", {})
        completed_tools[tool_key] = result
        state.setVariable("completedToolCalls", completed_tools)
        state.setScratchpad(f"tool.{pending_step_id}.{pending_name}.result", result)
        state.setVariable("pendingCallId", None)
        state.setVariable("pendingToolName", None)
        state.setVariable("pendingArguments", None)
        state.setVariable("pendingStepId", None)
        plan = ExecutionPlan.model_validate(state.getVariable("executionPlan"))
        budget = ExecutionBudget(self.executionLimits)

        try:
            final_text, reasoning, sources, content_blocks, actions = await self._executeGraphStatic(
                plan,
                state,
                budget,
            )
            final_text = self.outputPolicy(final_text, principal)
            content_blocks = self._applyOutputPolicy(content_blocks, final_text)
        except SuspensionSignal as signal:
            self._recordTerminal(
                state,
                "requires_action",
                "external_tool",
                callId=signal.call_id,
                toolName=signal.name,
            )
            response = OutputSynthesizer.synthesizeStatic(
                runId=run_id,
                content="",
                reasoningLogs=state.getVariable("reasoningLogs", []),
                actions=state.getVariable("actions", []),
                responseStatus="requires_action",
                status="requires_action",
                events=state.getVariable("events", []),
                functionCalls=[FunctionCall(
                    call_id=signal.call_id,
                    name=signal.name,
                    arguments=signal.arguments,
                )],
            )
            resume_cache[output.call_id] = response.model_dump(by_alias=True, exclude_none=True)
            state.setVariable("resumeCache", resume_cache)
            payload = state.exportState()
            payload["status"] = "suspended"
            payload.update({
                "pendingCallId": signal.call_id,
                "pendingToolName": signal.name,
                "pendingArguments": signal.arguments,
                "pendingStepId": state.getVariable("pendingStepId"),
            })
            self.checkpointStore.save(principal.tenant_id, run_id, "suspended", payload)
            return response
        except asyncio.CancelledError:
            self._recordTerminal(state, "cancelled", "request_cancelled")
            raise
        except Exception as exc:
            self._recordTerminal(
                state,
                "failed",
                type(exc).__name__,
                errorType=type(exc).__name__,
            )
            raise

        response = OutputSynthesizer.synthesizeStatic(
            runId=run_id,
            content=content_blocks,
            reasoningLogs=reasoning,
            actions=actions,
            sources=sources,
            status=budget.terminal_status,
            metrics={"stepsExecuted": budget.steps, "terminationReason": budget.termination_reason, **budget.metrics()},
            events=state.getVariable("events", []),
            failures=state.getVariable("failures", []),
            terminationReason=budget.termination_reason,
        )
        if include_suggestions and response.status == "completed" and response.content:
            response.suggestions = await self._generateFollowUpSuggestions(response)
        resume_cache[output.call_id] = response.model_dump(by_alias=True, exclude_none=True)
        state.setVariable("resumeCache", resume_cache)
        terminalStatus = "failed" if budget.terminal_status == "failed" else "completed"
        self._recordTerminal(
            state,
            terminalStatus,
            budget.termination_reason,
            stepsExecuted=budget.steps,
            toolCallCount=budget.tool_calls,
        )
        payload = state.exportState()
        payload["status"] = terminalStatus
        payload["resumeCache"] = resume_cache
        self.checkpointStore.save(principal.tenant_id, run_id, "suspended", payload)
        return response

    async def _executeGraphStreamWithCancellation(
        self,
        plan: ExecutionPlan,
        state: ExecutionState,
        budget: ExecutionBudget,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        runStartedAt = None
        runTerminal = False
        try:
            async for event in self._executeGraphStream(plan, state, budget):
                event_type = event.get("type")
                event_data = event.get("data", {})
                if event_type == "status" and isinstance(event_data, dict) and event_data.get("status") == "started":
                    runStartedAt = event_data.get("startedAt")
                if (
                    event_type == "status"
                    and isinstance(event_data, dict)
                    and event_data.get("status") in {"completed", "failed", "cancelled", "requires_action"}
                    and not runTerminal
                ):
                    self._recordTerminal(
                        state,
                        str(event_data["status"]),
                        event_data.get("terminationReason"),
                        stepCount=event_data.get("stepCount", budget.steps),
                        toolCallCount=event_data.get("toolCallCount", budget.tool_calls),
                    )
                    runTerminal = True
                yield event
        except asyncio.CancelledError:
            if not runTerminal:
                data = {
                    "status": "cancelled",
                    "startedAt": runStartedAt,
                    "endedAt": self._timestamp(),
                    "stepCount": budget.steps,
                    "toolCallCount": budget.tool_calls,
                }
                self._recordTerminal(
                    state,
                    "cancelled",
                    "client_disconnected",
                    **{key: value for key, value in data.items() if key != "status"},
                )
                yield {"type": "status", "data": data}
            raise
        except GeneratorExit:
            if not runTerminal:
                self._recordTerminal(
                    state,
                    "cancelled",
                    "stream_closed",
                    stepCount=budget.steps,
                    toolCallCount=budget.tool_calls,
                )
            raise
        except Exception as exc:
            if not runTerminal:
                data = {
                    "status": "failed",
                    "terminationReason": type(exc).__name__,
                    "startedAt": runStartedAt,
                    "endedAt": self._timestamp(),
                    "stepCount": budget.steps,
                    "toolCallCount": budget.tool_calls,
                }
                self._recordTerminal(state, "failed", type(exc).__name__, errorType=type(exc).__name__)
                yield {"type": "status", "data": data}
            logger.exception("Streaming run failed", extra={"run_id": state.runId})

    def _recordTerminal(
        self,
        state: ExecutionState,
        status: str,
        termination_reason: str | None = None,
        **details: Any,
    ) -> None:
        tenant_id = state.getVariable("tenantId")
        user_id = state.getVariable("userId")
        checkpoint_status = "suspended" if status == "requires_action" else status
        payload = state.exportState()
        payload["status"] = checkpoint_status
        if termination_reason is not None:
            payload["terminationReason"] = termination_reason
        if status == "requires_action":
            payload.update({
                "pendingCallId": state.getVariable("pendingCallId"),
                "pendingToolName": state.getVariable("pendingToolName"),
                "pendingArguments": state.getVariable("pendingArguments"),
                "pendingStepId": state.getVariable("pendingStepId"),
            })
        self.checkpointStore.save(tenant_id, state.runId, checkpoint_status, payload)
        event = "run.suspended" if status == "requires_action" else f"run.{status}"
        self.auditLog.record(
            event,
            state.runId,
            tenant_id,
            user_id,
            terminationReason=termination_reason,
            **details,
        )
        if self.metrics is not None:
            started = state.getVariable("startedMonotonic", time.monotonic())
            duration = max(0.0, time.monotonic() - float(started))
            outputs = state.getVariable("executionOutputHistory", [])
            output_text = "".join(str(item) for item in outputs)
            self.metrics.record_run(
                status,
                duration,
                int(details.get("toolCallCount", state.getVariable("toolCallCount", 0))),
                len(output_text) // 4,
            )

    @staticmethod
    def _validateInput(prompt: str, _principal: Principal) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise RequestContractError("A non-empty prompt is required.")
        if len(prompt) > 8000:
            raise RequestContractError("Prompt exceeds the 8000-character limit.")

    @staticmethod
    def _validateOutput(content: str, _principal: Principal) -> str:
        if not isinstance(content, str):
            raise RuntimeError("Output policy received a non-text response")
        return content

    @staticmethod
    def _applyOutputPolicy(contentBlocks: list[dict[str, Any]], filteredText: str) -> list[dict[str, Any]]:
        nonTextBlocks = [
            block for block in contentBlocks
            if not isinstance(block, dict) or block.get("type") != "text"
        ]
        if filteredText.strip():
            nonTextBlocks.insert(0, {"type": "text", "text": filteredText.strip()})
        return nonTextBlocks

    @staticmethod
    def _principalFromState(state: ExecutionState) -> Principal:
        roles = state.getVariable("principalRoles", [])
        return Principal(
            user_id=state.getVariable("userId"),
            tenant_id=state.getVariable("tenantId"),
            roles=tuple(roles) if isinstance(roles, (list, tuple)) else (),
        )

    @staticmethod
    def _collectSources(state: ExecutionState, value: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        existing = state.getVariable("sources", [])
        previousKeys = {
            (str(item.get("url", "")), str(item.get("title", "")).casefold())
            for item in existing
            if isinstance(item, dict)
        }
        sources = [
            source.model_dump(by_alias=True, exclude_none=True)
            for source in normalize_sources([existing, value])
        ]
        newSources = [
            source for source in sources
            if (str(source.get("url", "")), str(source.get("title", "")).casefold()) not in previousKeys
        ]
        state.setVariable("sources", sources)
        return sources, newSources

    def _isInternalTool(self, toolName: str, state: ExecutionState) -> bool:
        names = getattr(self.toolRegistry, "names", None)
        if callable(names):
            return toolName in names()
        return toolName not in state.getVariable("externalToolNames", [])

    async def _executeToolCall(
        self, toolName: str, state: ExecutionState, budget: ExecutionBudget | None = None,
    ) -> Any:
        arguments = state.getVariable("currentToolArguments")
        if not isinstance(arguments, dict):
            arguments = state.getVariable("toolArguments", {}).get(toolName, {})
        if self._isInternalTool(toolName, state):
            if budget is not None:
                budget.record_tool_call(toolName, arguments)
            with tracer.start_as_current_span("orchestrator.tool") as span:
                span.set_attribute("tool.name", toolName)
                result = await self.toolExecutor.executeAsync({
                    "function": {"name": toolName, "arguments": arguments},
                }, context={
                    "tenant_id": state.getVariable("tenantId"),
                    "user_id": state.getVariable("userId"),
                })
            if isinstance(result, ToolResult):
                result = result.toDict()
            if isinstance(result, dict) and result.get("code") == "INVALID_ARGUMENTS":
                self.auditLog.record(
                    "action.invalid_arguments",
                    state.runId,
                    state.getVariable("tenantId"),
                    state.getVariable("userId"),
                    toolName=toolName,
                    errorPath=result.get("metadata", {}).get("path", []),
                )
            return result
        if (
            state.getVariable("topology") == ExecutionTopology.INTERACTIVE.value
            and toolName in state.getVariable("externalToolNames", [])
        ):
            call_id = f"call_{uuid.uuid4().hex[:12]}"
            serialized_arguments = json.dumps(arguments, ensure_ascii=True, separators=(",", ":"))
            pending_step_id = int(state.getVariable("currentStepId"))
            state.setVariable("pendingCallId", call_id)
            state.setVariable("pendingToolName", toolName)
            state.setVariable("pendingArguments", serialized_arguments)
            state.setVariable("pendingStepId", pending_step_id)
            checkpoint = state.exportState()
            checkpoint.setdefault("variables", {})["sessionHistory"] = state.getVariable("sessionHistory", [])
            checkpoint.update({
                "status": "suspended",
                "pendingCallId": call_id,
                "pendingToolName": toolName,
                "pendingArguments": serialized_arguments,
                "pendingStepId": pending_step_id,
            })
            self.checkpointStore.save(
                state.getVariable("tenantId"),
                state.runId,
                "suspended",
                checkpoint,
            )
            self.auditLog.record(
                "run.suspended",
                state.runId,
                state.getVariable("tenantId"),
                state.getVariable("userId"),
                callId=call_id,
                toolName=toolName,
                stepId=pending_step_id,
            )
            raise SuspensionSignal(call_id, toolName, serialized_arguments)
        raise ValueError(f"Unknown tool: {toolName}")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _attachmentPromptBlock(contents: list[dict[str, str]], historyBlock: str) -> str:
        sections = []
        if historyBlock:
            sections.append(historyBlock[:8000])
        if contents:
            sections.append("## Attachment contents\n" + "\n".join(
                f"### {item['fileName']} ({item['fileId']})\n{item['content'][:4000]}"
                for item in contents
            )[:12000])
        return "\n\n".join(sections)

    async def _inlineMediaResult(self, value: Any, modality: str, instruction: str) -> dict[str, Any]:
        if isinstance(value, dict):
            data = value.get("data") if isinstance(value.get("data"), dict) else value
            if isinstance(data.get("mediaData"), str):
                for key in ("url", "imageUrl", "fileUrl", "mediaUrl", "outputPath", "path"):
                    data.pop(key, None)
                mimeType = str(data.get("mimeType") or "")
                if not mimeType:
                    raise MediaConversionError("Generated media has no MIME type", "MIME_MISMATCH")
                inline = self.mediaConverter.fromBase64(
                    data["mediaData"],
                    mimeType,
                    str(data.get("fileName") or "asset"),
                )
            else:
                converted = await self.toolExecutor.normalizeMediaResult({
                    "mediaType": modality if modality in {"image", "video", "audio"} else "file",
                    **value,
                })
                data = converted.get("data") if isinstance(converted, dict) and isinstance(converted.get("data"), dict) else converted
                if not isinstance(data, dict) or not data.get("mediaData"):
                    raise MediaConversionError("Generated media did not contain inline bytes", "MEDIA_CONVERSION_FAILED")
                mimeType = str(data.get("mimeType") or "")
                if not mimeType:
                    raise MediaConversionError("Generated media has no MIME type", "MIME_MISMATCH")
                inline = self.mediaConverter.fromBase64(
                    data["mediaData"],
                    mimeType,
                    str(data.get("fileName") or "asset"),
                )
            blockType = str(data.get("mediaType", data.get("type", modality)))
            if blockType not in {"image", "video", "audio", "file"}:
                blockType = modality if modality in {"image", "video", "audio"} else "file"
            expectedMimePrefix = {
                "image": "image/",
                "video": "video/",
                "audio": "audio/",
            }.get(blockType)
            if expectedMimePrefix and not inline.mimeType.startswith(expectedMimePrefix):
                raise MediaConversionError("Generated media MIME type does not match its block type", "MIME_MISMATCH")
            return {
                "type": blockType,
                "mediaData": inline.mediaData,
                "mimeType": inline.mimeType,
                "fileName": inline.fileName,
                "fileSizeBytes": inline.fileSizeBytes,
                "altText": instruction,
                "metadata": {"sha256": inline.sha256},
            }
        if not isinstance(value, str):
            raise MediaConversionError("Generated media reference is unsupported", "MEDIA_CONVERSION_FAILED")
        if value.startswith(("https://", "http://")):
            inline = await self.mediaConverter.fromUrl(value)
        else:
            from orchestrator.sandbox.pathPolicy import safePath

            inline = self.mediaConverter.fromFile(safePath(value, mode="read"))
        expected = "image/" if modality == "image" else "audio/" if modality == "audio" else None
        if expected and not inline.mimeType.startswith(expected):
            raise MediaConversionError("Generated media MIME type does not match its modality", "MIME_MISMATCH")
        return {
            "type": modality if modality in {"image", "video", "audio"} else "file",
            "mediaData": inline.mediaData,
            "mimeType": inline.mimeType,
            "fileName": inline.fileName,
            "fileSizeBytes": inline.fileSizeBytes,
            "altText": instruction,
            "metadata": {"sha256": inline.sha256},
        }

    def _actionEvent(
        self,
        toolName: str,
        action: dict[str, Any],
        status: str,
        startedAt: str,
        endedAt: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        success = bool((result or {}).get("success", True))
        data = {
            **action,
            "status": status,
            "startedAt": startedAt,
            "endedAt": endedAt,
        }
        if status in {"completed", "failed"} and not success:
            data["error"] = {
                "code": str((result or {}).get("code") or (result or {}).get("errorCode") or "ACTION_FAILED"),
                "message": "The action could not be completed",
            }
        return {"type": "action", "data": data}

    def _safeActionFor(self, toolName: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.toolRegistry.actionFor(toolName, arguments)
        except (AttributeError, KeyError, TypeError, ValueError):
            return {
                "actionId": f"A{uuid.uuid4().hex[:5].upper()}",
                "actionType": "tool",
                "toolName": toolName,
                "message": f"Running {toolName}",
                "metadata": {},
            }

    @staticmethod
    def _legacyToolThought(action: dict[str, Any], toolName: str, result: dict[str, Any]) -> dict[str, Any]:
        actionId = str(action["actionId"])
        message = str(action.get("message") or f"Completed {toolName.replace('_', ' ')}")
        return {
            "type": "thought",
            "data": {
                "id": f"T{actionId[1:]}",
                "type": "thought",
                "message": message,
                "status": "completed",
                "data": {
                    "actionId": actionId,
                    "toolName": toolName,
                    "success": bool(result.get("success", True)),
                    "deprecated": True,
                },
            },
        }

    async def _executeGraphStatic(
        self, 
        plan: ExecutionPlan, 
        state: ExecutionState,
        budget: ExecutionBudget | None = None
    ) -> tuple:
        """
        Executes the DAG steps sequentially or in parallel for static response mode.
        """
        budget = budget or ExecutionBudget(self.executionLimits)
        reasoningLogs = state.getVariable("reasoningLogs", [])
        actions = state.getVariable("actions", [])
        timeline = state.getVariable("events", [])
        sources = state.getVariable("sources", [])
        mediaAssets = state.getVariable("mediaAssets", [])
        contentBlocks = state.getVariable("contentBlocks", [])
        attachmentContents = state.getVariable("attachmentContents", [])
        historyBlock = SessionManager(
            state.getVariable("sessionId", ""),
            state.getVariable("sessionHistory", []),
        ).prompt_block(max_chars=8000)
        accumulatedText = state.getVariable("accumulatedText", "")
        completed_steps = {int(item) for item in state.getVariable("completedStepIds", [])}
        completed_tools = state.getVariable("completedToolCalls", {})
        if not timeline:
            timeline.extend([
                {"type": "status", "status": "started", "startedAt": self._timestamp()},
                {"type": "status", "status": "planned", "stepCount": len(plan.steps)},
            ])

        for step in self._orderedSteps(plan):
            if step.step_id in completed_steps:
                continue
            state.setVariable("currentStepId", step.step_id)
            fingerprint = budget.fingerprint(step.modality, step.capability, step.task_instruction)
            try:
                budget.begin_action(fingerprint, step.task_instruction)
            except ExecutionLimitError as exc:
                reasoningLogs.append({
                    "id": "T9N3Q7", "type": "thought", "message": "Execution paused at a safety limit",
                    "status": "completed",
                    "data": {"stepId": step.step_id, "reason": exc.reason},
                })
                timeline.append({"type": "thought", **reasoningLogs[-1]})
                break
            reasoningLogs.append({
                "id": "T9N3Q7", "type": "thought",
                "message": f"Working on {step.capability.replace('_', ' ')}",
                "status": "completed",
                "data": {"stepId": step.step_id, "modality": step.modality},
            })
            timeline.append({"type": "thought", **reasoningLogs[-1]})
            state.setVariable("reasoningLogs", reasoningLogs)

            tool_names = step.tool_calls or []
            if tool_names:
                toolResults = []
                for toolName in tool_names:
                    tool_key = f"{step.step_id}:{toolName}"
                    was_completed = tool_key in completed_tools
                    if was_completed:
                        toolResult = completed_tools[tool_key]
                    else:
                        state.setVariable(
                            "currentToolArguments",
                            step.tool_arguments.get(toolName)
                            or state.getVariable("toolArguments", {}).get(toolName, {}),
                        )
                        try:
                            toolResult = await self._executeToolCall(toolName, state, budget)
                        except ExecutionLimitError:
                            if budget.termination_reason == "Maximum tool-call budget exceeded":
                                budget.terminal_status = "failed"
                                budget.termination_reason = "tool_call_limit"
                            action = self._safeActionFor(
                                toolName, state.getVariable("currentToolArguments", {}),
                            )
                            failedAction = self._actionEvent(
                                toolName, action, "failed", self._timestamp(), self._timestamp(),
                                {"success": False, "code": "TOOL_CALL_LIMIT"},
                            )["data"]
                            actions.append(failedAction)
                            timeline.append({"type": "action", **failedAction})
                            state.setVariable("actions", actions)
                            state.setVariable("events", timeline)
                            self.auditLog.record(
                                "run.failed", state.runId, state.getVariable("tenantId"), state.getVariable("userId"),
                                terminationReason=budget.termination_reason, toolName=toolName,
                            )
                            break
                        completed_tools[tool_key] = toolResult
                        state.setVariable("completedToolCalls", completed_tools)
                    toolResults.append(toolResult)
                    sources, _ = self._collectSources(state, toolResult)
                    state.setScratchpad(f"tool.{step.step_id}.{toolName}.result", toolResult)
                    if not was_completed:
                        budget.record_output(toolResult)
                    if self._isInternalTool(toolName, state):
                        action = toolResult.get("metadata", {}).get("action")
                        if not isinstance(action, dict):
                            action = self._safeActionFor(toolName, state.getVariable("currentToolArguments", {}))
                        if not was_completed:
                            actions.append(self._actionEvent(
                                toolName,
                                action,
                                "failed" if not toolResult.get("success", True) else "completed",
                                self._timestamp(),
                                self._timestamp(),
                                toolResult,
                            )["data"])
                            timeline.append({"type": "action", **actions[-1]})
                            reasoningLogs.append(self._legacyToolThought(action, toolName, toolResult)["data"])
                            timeline.append({"type": "thought", **reasoningLogs[-1]})
                    state.setVariable("actions", actions)
                    state.setVariable("reasoningLogs", reasoningLogs)
                    if not toolResult.get("success", True):
                        budget.terminal_status = "failed"
                        budget.termination_reason = "tool_execution_failed"
                        break
                state.recordStepOutput(step.step_id, toolResults)
                completed_steps.add(step.step_id)
                state.setVariable("completedStepIds", sorted(completed_steps))
                state.setVariable("accumulatedText", accumulatedText)
                if budget.terminal_status == "failed":
                    break
                continue

            # Resolve inputs from prior steps if dependency exists
            stepInput = step.task_instruction
            promptContext = self._attachmentPromptBlock(attachmentContents, historyBlock)
            if promptContext:
                stepInput = f"{stepInput}\n\n{promptContext}"
            if step.depends_on:
                for parentId in step.depends_on:
                    parentOutput = state.getStepOutput(parentId)
                    stepInput = f"{stepInput}\n\nContext from previous step: {parentOutput}"

            # Dispatcher hook simulation (routes to text, canvas, voice, etc.)
            agent = self.agentRegistry.resolve(step.capability, step.modality)
            try:
                if agent is not None:
                    stepResult = await asyncio.wait_for(self.agentRegistry.collaborate(
                        agent=agent,
                        instruction=stepInput,
                        state=state,
                        task_id=step.step_id,
                    ), timeout=max(0.001, budget.limits.max_runtime_seconds))
                else:
                    stepResult = await asyncio.wait_for(self._dispatchStep(step.modality, stepInput), timeout=max(0.001, budget.limits.max_runtime_seconds))
            except asyncio.TimeoutError as exc:
                budget._stop("Step execution timeout exceeded")
                raise ExecutionLimitError("Step execution timeout exceeded", budget.metrics()) from exc
            
            if step.modality in {"image", "audio", "video"}:
                try:
                    inlineBlock = await self._inlineMediaResult(stepResult, step.modality, step.task_instruction)
                except (MediaConversionError, OSError, ValueError) as exc:
                    budget.terminal_status = "failed"
                    budget.termination_reason = "MEDIA_CONVERSION_FAILED"
                    failures = state.getVariable("failures", [])
                    failures.append({"code": "MEDIA_CONVERSION_FAILED", "message": str(exc)})
                    state.setVariable("failures", failures)
                    break
                stepResult = inlineBlock
                contentBlocks.append(inlineBlock)
                state.setVariable("contentBlocks", contentBlocks)

            # Store step output in state bus
            state.recordStepOutput(step.step_id, stepResult)
            sources, _ = self._collectSources(state, stepResult)
            completed_steps.add(step.step_id)
            state.setVariable("completedStepIds", sorted(completed_steps))
            budget.record_output(stepResult)
            outputs = state.getVariable("executionOutputHistory", []) + [stepResult]
            state.setVariable("executionOutputHistory", outputs)

            if budget.iterations % 3 == 0:
                scores = state.getVariable("evaluationScores", [])
                evaluation = await ExecutionEvaluator(self.textDispatcher).evaluate_async(
                    state.getVariable("originalPrompt", ""),
                    outputs,
                    scores,
                )
                scores.append(evaluation.progress_score)
                state.setVariable("evaluationScores", scores)
                reasoningLogs.append({
                    "id": "T9N3Q7", "type": "thought",
                    "message": "Reviewing progress before continuing",
                    "status": "completed",
                    "data": {"stepId": step.step_id, "decision": evaluation.decision},
                })
                timeline.append({"type": "thought", **reasoningLogs[-1]})
                if evaluation.decision == "stop":
                    budget.termination_reason = evaluation.reasoning
                    budget.terminal_status = "stopped_budget"
                    break
                if evaluation.decision == "summarize":
                    budget.termination_reason = evaluation.reasoning
                    budget.terminal_status = "summarized"
                    accumulatedText += "\n\nExecution paused at the observed progress plateau: " + evaluation.reasoning
                    break

            if step.modality == "text":
                accumulatedText += f"\n{stepResult}"
                if str(stepResult).strip():
                    contentBlocks.append({"type": "text", "text": str(stepResult).strip()})

            state.setVariable("reasoningLogs", reasoningLogs)
            state.setVariable("actions", actions)
            state.setVariable("sources", sources)
            state.setVariable("mediaAssets", mediaAssets)
            state.setVariable("contentBlocks", contentBlocks)
            state.setVariable("events", timeline)
            state.setVariable("accumulatedText", accumulatedText)

        terminalStatus = "failed" if budget.terminal_status == "failed" else "completed"
        timeline.append({
            "type": "status",
            "status": terminalStatus,
            "terminationReason": budget.termination_reason,
            "stepCount": budget.steps,
            "toolCallCount": budget.tool_calls,
            "endedAt": self._timestamp(),
        })
        state.setVariable("events", timeline)
        return accumulatedText.strip(), reasoningLogs, sources, contentBlocks, actions

    async def _executeGraphStream(
        self, 
        plan: ExecutionPlan, 
        state: ExecutionState,
        budget: ExecutionBudget | None = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Asynchronously yields execution events for real-time streaming mode.
        """
        budget = budget or ExecutionBudget(self.executionLimits)
        runStartedAt = self._timestamp()
        yield {"type": "status", "data": {"status": "started", "startedAt": runStartedAt}}
        yield {"type": "status", "data": {"status": "planned", "startedAt": runStartedAt, "stepCount": len(plan.steps)}}
        toolCallCount = 0
        completed_steps = {int(item) for item in state.getVariable("completedStepIds", [])}
        completed_tools = state.getVariable("completedToolCalls", {})
        for step in self._orderedSteps(plan):
            if step.step_id in completed_steps:
                continue
            state.setVariable("currentStepId", step.step_id)
            fingerprint = budget.fingerprint(step.modality, step.capability, step.task_instruction)
            try:
                budget.begin_action(fingerprint, step.task_instruction)
            except ExecutionLimitError as exc:
                yield {"type": "thought", "data": {
                    "id": "T9N3Q7", "type": "thought", "message": "Execution paused at a safety limit",
                    "status": "completed",
                    "data": {"reason": exc.reason, "metrics": budget.metrics()},
                }}
                yield {"type": "status", "data": {
                    "status": "completed", "terminationReason": exc.reason,
                    "startedAt": runStartedAt, "endedAt": self._timestamp(),
                    "stepCount": budget.steps, "toolCallCount": toolCallCount,
                }}
                return
            # Yield thought/status event
            yield {
                "type": "thought",
                "data": {
                    "id": "T9N3Q7", "type": "thought",
                    "message": f"Working on {step.capability.replace('_', ' ')}",
                    "status": "started",
                    "data": {"stepId": step.step_id, "modality": step.modality},
                }
            }
            yield {
                "type": "thought",
                "data": {
                    "id": "T9N3Q7", "type": "thought",
                    "message": f"Processing {step.capability.replace('_', ' ')}",
                    "status": "processing",
                    "data": {"stepId": step.step_id, "modality": step.modality},
                },
            }

            tool_names = step.tool_calls or []
            if tool_names:
                toolResults = []
                for toolName in tool_names:
                    tool_key = f"{step.step_id}:{toolName}"
                    if tool_key in completed_tools:
                        toolResult = completed_tools[tool_key]
                        toolResults.append(toolResult)
                        _sources, newSources = self._collectSources(state, toolResult)
                        for source in newSources:
                            yield {"type": "source", "data": source}
                        continue
                    arguments = step.tool_arguments.get(toolName) or state.getVariable("toolArguments", {}).get(toolName, {})
                    state.setVariable("currentToolArguments", arguments)
                    if not self._isInternalTool(toolName, state):
                        try:
                            await self._executeToolCall(toolName, state)
                        except SuspensionSignal as signal:
                            yield {
                                "type": "function_call",
                                "data": {
                                    "type": "function_call",
                                    "call_id": signal.call_id,
                                    "name": signal.name,
                                    "arguments": signal.arguments,
                                },
                            }
                            yield {"type": "status", "data": {
                                "status": "requires_action",
                                "startedAt": runStartedAt,
                                "endedAt": self._timestamp(),
                                "stepCount": budget.steps,
                                "toolCallCount": toolCallCount,
                            }}
                            return
                    action = self._safeActionFor(toolName, arguments)
                    startedAt = self._timestamp()
                    yield self._actionEvent(toolName, action, "started", startedAt)
                    yield self._actionEvent(toolName, action, "processing", startedAt)
                    try:
                        toolResult = await self._executeToolCall(toolName, state, budget)
                    except ExecutionLimitError:
                        budget.terminal_status = "failed"
                        budget.termination_reason = "tool_call_limit"
                        self.auditLog.record(
                            "run.failed", state.runId, state.getVariable("tenantId"), state.getVariable("userId"),
                            terminationReason="tool_call_limit", toolName=toolName,
                        )
                        yield self._actionEvent(
                            toolName, action, "failed", startedAt, self._timestamp(),
                            {"success": False, "code": "TOOL_CALL_LIMIT"},
                        )
                        yield {"type": "status", "data": {
                            "status": "failed", "terminationReason": "tool_call_limit",
                            "startedAt": runStartedAt, "endedAt": self._timestamp(),
                            "stepCount": budget.steps, "toolCallCount": budget.tool_calls,
                        }}
                        return
                    completed_tools[tool_key] = toolResult
                    state.setVariable("completedToolCalls", completed_tools)
                    toolCallCount += 1
                    toolResults.append(toolResult)
                    _sources, newSources = self._collectSources(state, toolResult)
                    for source in newSources:
                        yield {"type": "source", "data": source}
                    actionResult = toolResult.get("metadata", {}).get("action")
                    if isinstance(actionResult, dict):
                        action = actionResult
                    endedAt = self._timestamp()
                    yield self._actionEvent(
                        toolName, action,
                        "completed" if toolResult.get("success", True) else "failed",
                        startedAt, endedAt, toolResult,
                    )
                    yield self._legacyToolThought(action, toolName, toolResult)
                    if not toolResult.get("success", True):
                        budget.terminal_status = "failed"
                        budget.termination_reason = "tool_execution_failed"
                        yield {"type": "status", "data": {
                            "status": "failed", "terminationReason": budget.termination_reason,
                            "startedAt": runStartedAt, "endedAt": self._timestamp(),
                            "stepCount": budget.steps, "toolCallCount": toolCallCount,
                        }}
                        state.recordStepOutput(step.step_id, toolResults)
                        return
                state.recordStepOutput(step.step_id, toolResults)
                completed_steps.add(step.step_id)
                state.setVariable("completedStepIds", sorted(completed_steps))
                continue

            # Route through the most appropriate collaborative agent.
            agent = self.agentRegistry.resolve(step.capability, step.modality)
            stepInstruction = step.task_instruction
            promptContext = self._attachmentPromptBlock(
                state.getVariable("attachmentContents", []),
                SessionManager(
                    state.getVariable("sessionId", ""),
                    state.getVariable("sessionHistory", []),
                ).prompt_block(max_chars=8000),
            )
            if promptContext:
                stepInstruction = f"{stepInstruction}\n\n{promptContext}"
            try:
                if step.modality == "text":
                    if agent is not None:
                        chunkGenerator = agent.stream(stepInstruction, state, step.step_id)
                    else:
                        dispatcher = self.dispatcherRegistry.get("text")
                        streamer = getattr(dispatcher, "stream", None)
                        if not callable(streamer):
                            raise RuntimeError("Text dispatcher does not support token streaming")
                        chunkGenerator = streamer(stepInstruction)
                    streamedParts: list[str] = []
                    try:
                        while True:
                            try:
                                chunk = await asyncio.wait_for(
                                    chunkGenerator.__anext__(),
                                    timeout=max(0.001, budget.limits.max_runtime_seconds),
                                )
                            except StopAsyncIteration:
                                break
                            filteredChunk = self.outputPolicy(chunk, self._principalFromState(state))
                            if not isinstance(filteredChunk, str):
                                raise RuntimeError("Output policy returned a non-text stream chunk")
                            streamedParts.append(filteredChunk)
                            if filteredChunk:
                                yield {"type": "textChunk", "data": {"content": filteredChunk}}
                    finally:
                        closeStream = getattr(chunkGenerator, "aclose", None)
                        if callable(closeStream):
                            await closeStream()
                    stepResult = "".join(streamedParts).strip()
                elif agent is not None:
                    stepResult = await asyncio.wait_for(self.agentRegistry.collaborate(
                        agent=agent,
                        instruction=stepInstruction,
                        state=state,
                        task_id=step.step_id,
                    ), timeout=max(0.001, budget.limits.max_runtime_seconds))
                else:
                    stepResult = await asyncio.wait_for(self._dispatchStep(step.modality, stepInstruction), timeout=max(0.001, budget.limits.max_runtime_seconds))
            except asyncio.TimeoutError as exc:
                budget._stop("Step execution timeout exceeded")
                yield {"type": "thought", "data": {
                    "id": "T9N3Q7", "type": "thought", "message": "A step exceeded its time limit",
                    "status": "completed",
                    "data": {"reason": "Step execution timeout exceeded", "metrics": budget.metrics()},
                }}
                yield {"type": "status", "data": {
                    "status": "failed", "terminationReason": "Step execution timeout exceeded",
                    "startedAt": runStartedAt, "endedAt": self._timestamp(),
                    "stepCount": budget.steps, "toolCallCount": toolCallCount,
                }}
                return
            state.recordStepOutput(step.step_id, stepResult)
            _sources, newSources = self._collectSources(state, stepResult)
            for source in newSources:
                yield {"type": "source", "data": source}
            completed_steps.add(step.step_id)
            state.setVariable("completedStepIds", sorted(completed_steps))
            budget.record_output(stepResult)
            outputs = state.getVariable("executionOutputHistory", []) + [stepResult]
            state.setVariable("executionOutputHistory", outputs)

            if budget.iterations % 3 == 0:
                scores = state.getVariable("evaluationScores", [])
                evaluation = await ExecutionEvaluator(self.textDispatcher).evaluate_async(
                    state.getVariable("originalPrompt", ""),
                    outputs,
                    scores,
                )
                scores.append(evaluation.progress_score)
                state.setVariable("evaluationScores", scores)
                yield {"type": "thought", "data": {
                    "id": "T9N3Q7", "type": "thought",
                    "message": "Reviewing progress before continuing",
                    "status": "processing",
                    "data": {"decision": evaluation.decision},
                }}
                if evaluation.decision == "stop":
                    budget.termination_reason = evaluation.reasoning
                    budget.terminal_status = "stopped_budget"
                    yield {"type": "status", "data": {
                        "status": "completed", "terminationReason": evaluation.reasoning,
                        "startedAt": runStartedAt, "endedAt": self._timestamp(),
                        "stepCount": budget.steps, "toolCallCount": toolCallCount,
                    }}
                    return
                if evaluation.decision == "summarize":
                    budget.termination_reason = evaluation.reasoning
                    budget.terminal_status = "summarized"
                    yield {"type": "status", "data": {
                        "status": "completed", "terminationReason": evaluation.reasoning,
                        "startedAt": runStartedAt, "endedAt": self._timestamp(),
                        "stepCount": budget.steps, "toolCallCount": toolCallCount,
                    }}
                    return

            if step.modality != "text":
                try:
                    inlineBlock = await self._inlineMediaResult(stepResult, step.modality, step.task_instruction)
                except (MediaConversionError, OSError, ValueError):
                    budget.terminal_status = "failed"
                    budget.termination_reason = "MEDIA_CONVERSION_FAILED"
                    self.auditLog.record(
                        "run.failed", state.runId, state.getVariable("tenantId"), state.getVariable("userId"),
                        terminationReason="MEDIA_CONVERSION_FAILED",
                    )
                    yield {"type": "status", "data": {
                        "status": "failed", "terminationReason": "MEDIA_CONVERSION_FAILED",
                        "startedAt": runStartedAt, "endedAt": self._timestamp(),
                        "stepCount": budget.steps, "toolCallCount": budget.tool_calls,
                    }}
                    return
                yield {
                    "type": "thought",
                    "data": {
                        "id": "T0A1B2", "type": "thought", "message": "Created a media asset",
                        "status": "completed",
                        "data": {"mediaType": step.modality},
                    },
                }
                yield {"type": "media", "data": inlineBlock}

        yield {"type": "status", "data": {
            "status": "failed" if budget.terminal_status == "failed" else "completed",
            "terminationReason": budget.termination_reason,
            "startedAt": runStartedAt, "endedAt": self._timestamp(),
            "stepCount": budget.steps, "toolCallCount": budget.tool_calls,
        }}
    @staticmethod
    def _orderedSteps(plan: ExecutionPlan) -> list[ExecutionStep]:
        by_id = {step.step_id: step for step in plan.steps}
        ordered: list[ExecutionStep] = []
        completed: set[int] = set()

        while len(ordered) < len(plan.steps):
            ready = [step for step in plan.steps if step.step_id not in completed and all(parent_id in completed for parent_id in (step.depends_on or []))]
            if not ready:
                raise ExecutionLimitError("Execution plan contains a dependency cycle", {"steps": list(completed)})
            for step in ready:
                ordered.append(step)
                completed.add(step.step_id)

        return [by_id[step.step_id] for step in ordered]

    async def _dispatchStep(self, modality: str, instruction: str) -> str:
        """
        Internal routing handler to trigger the appropriate model dispatcher
        registered in the core model registry.
        """
        dispatcher = self.dispatcherRegistry.get(modality)
        if dispatcher is None:
            raise RuntimeError(f"No dispatcher configured for modality '{modality}'")
        generate = getattr(dispatcher, "generate", None)
        if not callable(generate):
            raise RuntimeError(f"Dispatcher for '{modality}' has no generate method")
        result = generate(instruction)
        if hasattr(result, "__await__"):
            result = await result
        if hasattr(result, "text"):
            result = result.text
        if isinstance(result, (dict, list)) and modality != "text":
            return result
        return str(result).strip()
