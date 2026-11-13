# Forge Orchestrator Runtime [PARTIAL]

This inventory documents implementation status, not production readiness.
Its older round-by-round sections are historical snapshots and may refer to
superseded module paths; the current serving architecture is summarized here
and decisions D-024 and D-025 take precedence.

## Current inference and data boundaries

```text
API / engine / tools
        │
        ▼
InferenceGateway ──► registry ──► source ──► backend
        ▲                               Hub / local path / artifact store
        │                               Transformers / modality runtimes
        └── stable requests, metrics, limits, lifecycle
```

Engine and tool inference calls use the gateway or modality facades. Hugging
Face Hub access is isolated to `inference/sources/`; model execution belongs
to `inference/backends/`. The app lifespan owns and closes one gateway.
Responses schemas are grouped under `schemas/v1/responses/`. Trajectory export
is opt-in, versioned, redacted, and bounded. See
[D-024](../decisions/D-024-multisource-inference-gateway.md) and
[D-025](../decisions/D-025-response-effort-suggestions-trajectories.md).

## Table of contents

- [Changelog](#changelog)
- [Status tags](#status-tags)
- [1. Executive summary](#1-executive-summary-partial)
- [2. Service boundary and packaging](#2-service-boundary--packaging-partial)
- [3. Directory and module map](#3-directory--module-map-partial)
- [4. HTTP layer](#4-http-layer--actual-vs-intended-partial)
- [5. Request contract](#5-request-contract-schemas-partial)
- [6. Engine construction and dependency injection](#6-engine-construction--dependency-injection-partial)
- [7. End-to-end request lifecycle](#7-end-to-end-request-lifecycle-forgeenginerun-and-resume-partial)
- [8. Agents](#8-agents-partial)
- [9. Tools](#9-tools-implemented)
- [10. Models and modality adapters](#10-models--modality-adapters-partial)
- [12. Configuration and environment](#12-configuration--environment-partial)
- [13. Observability](#13-observability-partial)
- [14. Tests](#14-tests-partial)
- [15. Gap register](#15-gap-register-partial)
- [16. Recommended next steps](#16-recommended-next-steps-planned)
- [Round 3 verification log](#round-3-verification-log-historical)
- [Round 4/5 verification log](#round-45-verification-log-implemented)
- [Open questions for reviewers](#open-questions-for-reviewers-planned)

## Changelog [IMPLEMENTED]

| Date | Author | Change type | Change |
|---|---|---|---|
| 2026-11-10 | Uwagbae | Changed | Round 29 — Moved the Open-Meteo client into the weather tool; `core/models/adapters` is for AI model integrations (D-023). |
| 2026-11-10 | Uwagbae | Changed | Round 28 — Removed the persistent state store and built-in `todo`/`memory` tools; callers provide stateful capabilities as external tools (D-022). |
| 2026-11-11 | Uwagbae | Changed | Round 27 — Implemented all registered operations; removed unavailable or unsafe operations; split `extract` and `summarize`; deleted `future_tools.py`; no registered handler returns `NOT_IMPLEMENTED` (D-021). |
| 2026-11-12 | Uwagbae | Added | Registered the `computer` tool on the isolated Firecracker backend; preserved the filesystem sandbox for existing tools; added a guest agent, bounded pool, policy checks, and Linux/KVM integration coverage (D-026). |
| 2026-11-10 | Uwagbae | Changed | Round 25/26 — D-020 requires `operation` on every registered tool; registered known missing domains as honest `NOT_IMPLEMENTED` placeholders; skills, Action IDs, and schema enforcement updated; D-019 annotated as partially superseded. |
| 2026-11-10 | Uwagbae | Decided | Round 23 — D-019 makes data operations one `data` tool and skill; documents the already consolidated image/video domains; adds tool/skill parity enforcement; D-009 annotated as partially superseded. |
| 2026-11-10 | Uwagbae | Changed | Round 15 — Removed MCP integration adapters and service skills; external service functions are caller-owned under D-004. Added bounded local JSON extraction/extractive summarization and expanded tool skills. |
| 2026-11-11 | Uwagbae | Changed | Consolidated image/video operations under one registered tool and skill each; added shared `transcribe`/`speak` handlers, authenticated batch audio endpoints, and push-to-talk `/v1/audio/sts`; migrated the Responses request fields and removed response titles. |
| 2026-11-11 | Uwagbae | Changed | Replaced remote speech calls with injected local faster-whisper/Piper dispatchers; separated speech/transcription routes; documented client-owned titles (D-012, D-013). |
| 2026-11-10 | Uwagbae | Changed | SSE timeline packets use the single `event` packet type with typed `OrchestratorEvent` data; input media is base64-only. |
| 2026-11-09 | Uwagbae | Added | Created source-grounded runtime inventory covering routes, schemas, construction, execution, security, and gaps. |
| 2026-11-09 | Uwagbae | Renamed | Corrected the legacy engine identifier to `ForgeEngine` (naming correction; no behavior change); `rg` sweep output: `No matches found`. |
| 2026-11-09 | Uwagbae | Added | Renamed imports/tests/README references and added source citations for constructor behavior, run signature, schemas, routes, and persistence. |
| 2026-11-09 | Uwagbae | Corrected | Distinguished the legacy sibling-tree traceback from current-package `test_forge.py` failures; documented exact current failure causes and summary. |
| 2026-11-09 | Uwagbae | Added | Added proposed lifespan, import-time work table, error taxonomy, concurrency audit, tool-argument trace, checkpoint example, dead-code inventory, and OpenAPI diff. |
| 2026-11-09 | Uwagbae | Verified | Rechecked dependency-audit tool availability, test results, generated OpenAPI, route module sizes, checkpoint root, and class-name sweep. |
| **Round 3 — Fixes & Verification** | | | |
| 2026-11-09 | Uwagbae | Fixed | Registered Canva's stable Thought IDs; `ForgeEngine()` now constructs while integration credentials/client initialization remain deferred until tool call. G-001 resolved. |
| 2026-11-09 | Uwagbae | Fixed | Constrained pytest discovery to this project's `tests/` and added the in-process smoke test; the suite now passes with local `test_eval.py` collection. |
| 2026-11-09 | Uwagbae | Added | Moved `sandbox/` to `src/orchestrator/sandbox/`; updated source, tests, and policy references. |
| 2026-11-09 | Uwagbae | Added | Mounted `/v1/orchestrate` as a request-validated 501 skeleton; generated OpenAPI now contains the route. |
| 2026-11-09 | Uwagbae | Removed | Deleted the unused `src/orchestrator/agents/title/` SDK path; `_generateTitle()` remains the implemented title path. |
| 2026-11-09 | Uwagbae | Verified | Full suite: `63 passed`; smoke test: `1 passed`; route-contract test passes; pytest collection is rooted in this project. |
| 2026-11-09 | Uwagbae | Changed | Replaced the external chat passthrough with Forge Text model completions; mounted registry-backed models and Hugging Face embeddings endpoints; request title option is `generateTitle`. |
| 2026-11-09 | Uwagbae | Changed | Made `/v1/chat/completions` and `/v1/models` use OpenAI-compatible request/response field shapes while retaining Forge/Hugging Face model inference; added model lookup by ID and standard generation parameters. |
| **Rounds 4/5 — Event Contract and Security Scope** | | | |
| 2026-11-09 | Uwagbae | Decided | Accepted D-001 through D-003: handler-owned IDs, separate Thought/Action/Status events, and removal of unwired approval/policy scaffolding. |
| 2026-11-09 | Uwagbae | Changed | Added Action lifecycle events and run Status events; static responses now separate reasoning Thoughts from Actions. |
| 2026-11-09 | Uwagbae | Changed | Deleted the obsolete `/v1/orchestrate` stub without moving it; `responses/routes.py` remains the engine/library module, not an HTTP router. |
| 2026-11-09 | Uwagbae | Removed | Deleted ApprovalStore, PolicyEngine, ABAC, egress helpers and their tests; retained RBAC, Principal, audit, checkpoint durability, and the core-backend identity resolver. |
| 2026-11-09 | Uwagbae | Verified | Post-Round-4/5 full suite: `59 passed`; focused Action/Thought/API-surface checks: `5 passed`. |
| **Rounds 6-8 — External Tools and Training Export** | | | |
| 2026-11-09 | Uwagbae | Added | D-004: caller-owned external tools suspend with `call_id`, atomic tenant-contained checkpoints, and resumable/idempotent continuation; the former internal service adapters were removed in Round 15. |
| 2026-11-09 | Uwagbae | Added | Initially mounted `/v1/responses` with authenticated-principal enforcement and a configured Chat Completions passthrough; the passthrough was later replaced by Forge Text inference; `/v1/orchestrate` remains absent. |
| 2026-11-09 | Uwagbae | Added | D-005: separated execution effort from topology and added per-request Responses-only training export, optional one-way Hugging Face upload, and lifespan shutdown. |
| 2026-11-09 | Uwagbae | Verified | Round 6-8 feature-focused tests: 30 passed; full-suite result is recorded after final validation. |
| **Rounds 9-11 — Wire, Content, and Media Contract** | | | |
| 2026-11-09 | Uwagbae | Changed | Public Responses fields use camelCase (with literal `call_id` compatibility); content is ordered text/media blocks and lifecycle output is one ordered `events` timeline. |
| 2026-11-09 | Uwagbae | Changed | Attachment text and recent history reach classifier/refiner/agent prompts under fixed caps; neither is persisted in checkpoints. Internal tool arguments are JSON-Schema validated and internal tool-call budgets are enforced. |
| 2026-11-09 | Uwagbae | Changed | Media is base64-inline inside the orchestration pipeline and response; allowlisted HTTPS current-turn attachment URLs are converted at ingress, and media references are normalized before serialization. |
| 2026-11-11 | Uwagbae | Changed | Added Round 16 audio endpoints and a push-to-talk STS WebSocket, consolidated image/video operations, and finalized the caller-tools request contract. |

### Current state after Rounds 4-8

- `/v1/responses` owns the orchestration request/response and supports
  external function calls with two-phase resume. `/v1/chat/completions` uses
  the registered Forge Text model and never calls training export; it uses
  OpenAI-compatible API shapes, not an OpenAI-hosted service.
- `/v1/models` lists the Forge model registry; `/v1/embeddings` uses the
  registered Forge Embed model through Hugging Face inference.
- `/v1/audio/transcriptions` and `/v1/audio/speech` call the shared speech
  tools; `/v1/audio/sts` wires transcription, `ForgeEngine.run`, and speech
  over an authenticated push-to-talk WebSocket.
- `/v1/orchestrate` remains deleted and is not aliased or relocated.
- `ForgeEngine` remains a library entry point in
  `src/orchestrator/api/v1/responses/routes.py`. It constructs without registry-level event
  ID metadata; there are no credentials for caller-owned service integrations.
- External tool definitions are planner schemas only. Local tools execute
  through `ToolRegistry`; caller-owned external calls persist a `suspended`
  checkpoint and return `call_id`, then resume with a matching output.
- Checkpoints use atomic writes, validate tenant/run components, enforce
  tenant-root containment, and expire after 30 days by default. Production
  must mount `FORGE_CHECKPOINT_ROOT` on persistent storage.
- Thoughts are reasoning/progress only. Actions have handler-owned `A` IDs and
  lifecycle events; run lifecycle uses Status events. Streams add
  `function_call` for caller-owned functions.
- Tool Thought events remain only as explicitly deprecated compatibility
  events for one release. See D-001 and D-002 and the references under
  `docs/references/`.
- Effort (`mode`) and execution topology are separate. Trajectory export is
  inactive unless the caller sets `trajectoryExport=true`; only completed
  autonomous `/v1/responses` runs qualify.
- Approval, policy, ABAC, and egress scaffolding has been removed. RBAC still
  gates `orchestrate:run`; the HTTP routes require a trusted
  `request.state.principal` populated by upstream authentication middleware.
- `/v1/responses` uses `tools`, nested `reasoning.effort`, and
  `function_call_output` items inside `messages`; `previous_response_id` and
  function `call_id` retain their required snake_case spellings. Training
  export is selected through `metadata.trainingExport`; client session IDs,
  topology, title options, and response titles are not exposed.
- Unified output uses ordered `content` blocks and one ordered `events` list;
  separate top-level `thoughts`, `actions`, and `mediaAssets` fields are not
  part of that response schema.

## Status tags [IMPLEMENTED]

- `[IMPLEMENTED]` — wired and reachable at runtime.
- `[PARTIAL]` — code exists, but only some paths are wired.
- `[LIBRARY ONLY]` — callable code exists, but the app/engine does not call it.
- `[UNWIRED]` — described or defined, but no current runtime path reaches it.
- `[PLANNED]` — referenced in comments or docs only.
- `[DEAD / STALE]` — empty, obsolete, or unreachable code; verify before removal.
- `[RISK]` — concrete security, correctness, or reliability concern.

## 1. Executive summary [PARTIAL]

- `src/orchestrator/api/__init__.py` mounts `/v1/responses`, `/v1/chat/completions`,
  `/v1/models`, `/v1/embeddings`, and the two batch audio endpoints; it also
  mounts the `/v1/audio/sts` WebSocket and
  creates/closes the engine and training exporter through lifespan.
- `ForgeEngine` is a library entry point inside `src/orchestrator/api/v1/responses/routes.py`; this file is not a mounted HTTP route module.
- Default `ForgeEngine()` construction succeeds with the built-in tool registry; it does not load caller-owned service adapters.
- Thought, Action, and Status events are distinct; Action lifecycle is included in streaming and static response shapes.
- Default text and image dispatchers have no providers. Speech tools use the
  Forge-local Piper and faster-whisper dispatchers with their registered local
  model defaults.
- Model weights are downloaded from the Hugging Face Hub and run locally.
  Public repositories need no Hub token; `HF_TOKEN` is only for gated or
  private repositories. No hosted inference API key is configured or required
  by the current project setup.
- The Responses handler binds `OrchestratorRequest`, invokes the engine, and
  returns `UnifiedOrchestratorResponse` or SSE when a trusted principal is
  available.
- The engine has working orchestration primitives for principal/RBAC checks, in-memory run state, classification, planning, local tool calls, external-tool suspension, agent selection, output synthesis, checkpoints, and audit records; several are bypassed or incomplete.
- Normalized image bytes are passed to a configured multimodal vision dispatcher; inline attachment bytes are excluded from checkpoint exports.
- Tool arguments come from caller-supplied `toolArguments`; the selected tool's JSON schema is validated before invocation, and internal calls count against the configured tool-call limit.
- Approval/policy, ABAC, and egress helpers were removed by D-003. The retained identity resolver is for the core backend; idempotency and persistent conversation storage remain unwired.
- Pytest is configured with `testpaths = ["tests"]` and collection remains project-local; final post-change test results are recorded below.

**Can an HTTP request be served end-to-end right now? Partially.** Responses
requests reach `ForgeEngine` when trusted upstream middleware populates a
`Principal`. Chat Completions and embeddings lazily download snapshots when
needed and run the declared local model runtime; a Hub token is needed only
for private repositories.

## 2. Service boundary & packaging [PARTIAL]

### Ownership [IMPLEMENTED]

- The calling Forge core backend owns accounts, product/API operations, and external services. The orchestrator owns model dispatch, request planning, specialist coordination, local tool execution, and response synthesis.
- This package has its own `requirements.txt`, Dockerfile, Python source, tests, and docs. It does not contain a durable conversation database or user/account system.
- The expected authenticated caller boundary is the core backend. The current FastAPI app does not enforce that boundary.

### Dependencies [IMPLEMENTED]

All entries in `requirements.txt` are version ranges (`>=` and `<`), not exact pins; there is no lock file or hash-pinned install in this project directory.

| Group | Declared packages |
|---|---|
| Web/API | `fastapi>=0.110,<1.0`, `python-multipart>=0.0.9,<1.0`, `uvicorn[standard]>=0.28,<1.0`, `pydantic>=2.6,<3.0`, `pydantic-settings>=2.2,<3.0` |
| HTTP/config | `httpx>=0.27,<1.0`, `python-dotenv>=1.0.1,<2.0` |
| Models and local tools | `openai-agents>=0.24,<1.0`, `ddgs>=9.0,<10.0`, `torch>=2.2,<3.0`, `transformers>=4.44,<5.0`, `diffusers>=0.30,<1.0`, `sentence-transformers>=3.0,<6.0`, `faster-whisper>=1.1,<2.0`, `piper-tts>=1.2,<2.0` |
| Data and reporting | `pandas>=2.2,<3.0`, `openpyxl>=3.1,<4.0`, `matplotlib>=3.8,<4.0`, `sqlalchemy>=2.0,<3.0` |
| Image/OCR/media | `Pillow>=10,<13`, `pytesseract>=0.3.10,<0.4` |
| Testing | No test-only dependency group is declared in `requirements.txt`; the exercised environment already has pytest. |

**Dependency health note [RISK]:** broad ranges permit dependency changes between builds; no lock/hashes establish repeatable resolution. This scan did not run a vulnerability database audit and makes no claim that a particular package version is vulnerable.

**Environment limitation [PARTIAL]:** Pylance currently selects the repository-level `.venv`, which has no importable packages and no `pip`; this causes `reportMissingImports` for runtime dependencies such as FastAPI, Pydantic, and HTTPX. An installed system Python 3.12 has those packages, but changing the interpreter through the available environment tools did not change Pylance's reported selection. In VS Code, select an interpreter that has this project's `requirements.txt` installed, or provision the intended virtual environment before analysis. Dependency reproducibility cannot be assessed until a project environment/lock is established (G-030). `pip-audit` is unavailable; no vulnerability claim is made.

### Container and startup [IMPLEMENTED]

`Dockerfile` uses `python:3.11-slim`, installs `build-essential`, `ffmpeg`, and `tesseract-ocr`, installs `requirements.txt`, copies the package, exposes port `8000`, and runs:

```text
uvicorn orchestrator.api:app --host 0.0.0.0 --port 8000
```

That command starts the FastAPI application; lifespan creates the engine and
mounted versioned routes. Deployment must still provide upstream identity
middleware and any provider credentials.

## 3. Historical pre-consolidation directory map [HISTORICAL]

The tree below records an earlier package layout and is retained as historical
context; its `core/`, top-level `skills/`, and `models/` paths are not current
directories. The active `src/orchestrator/` package layout is summarized in
the [project README](../../README.md). In particular, inference ownership now
belongs to `src/orchestrator/inference/`; no `orchestrator.models`
compatibility package is retained.

```text
docs/
  README.md                         Documentation guide and index
  architecture/
    README.md                       Architecture-document index
    orchestrator-runtime.md         This code-accurate runtime report
  openapi.json                      Generated API contract snapshot
  references/
    thought-contract.md             Thought, Action, and Status event contract
    thought-ids.md                  Reasoning-only Thought IDs
    action-ids.md                   Handler-owned Action IDs
  decisions/
    D-001-thoughts-at-action-site.md
    D-002-separate-thoughts-from-actions.md
    D-003-remove-unwired-policy-scaffolding.md
    D-004-external-tools-two-phase-resume.md
    D-005-training-export-scope.md
    D-011-speech-tools-and-local-sts.md
    D-012-forge-runs-local-speech-models.md
    D-013-title-generation-is-client-owned.md
    D-018-forge-runs-models-locally.md
  research/
    R-001-openai-audio-shapes.md
    R-002-openai-responses-shape.md
    R-003-anthropic-messages-api.md
    R-004-gemini-content-generation.md
    R-005-xai-responses-api.md
    R-006-faster-whisper.md
    R-007-piper-python-api.md
src/
  export/
    __init__.py                       Training exporter public API
    formatters.py                     OpenAI chat JSONL record formatter
    huggingface.py                    One-way full-file Hugging Face uploader
    training.py                       Optional async export queue and worker
  __init__.py                       Package marker; empty
  agents/
    __init__.py                     Specialist imports and default six-agent factory
    base.py                         BaseAgent, retries, scratchpad, messages, handoff
    registry.py                     Capability/modality scoring and collaboration wrapper
    coding/agent.py                 Coding specialist and unused SDK builder helper
    data/agent.py                   Data specialist
    document/agent.py               Document specialist
    media/agent.py                  Media specialist
    research/agent.py               Research specialist and unused SDK builder helper
    vision/agent.py                 Vision specialist
  api/
    __init__.py                     FastAPI lifespan and versioned router mounting
    health.py                       Empty; no health endpoints
    v1/chat/completions/http.py      Compatibility import for chat router
    v1/chat/completions/routes.py    Forge Text model Chat Completions
    v1/audio/speech/routes.py        Authenticated batch text-to-speech
    v1/audio/transcriptions/routes.py Authenticated batch speech-to-text
    v1/audio/sts/routes.py           Authenticated push-to-talk STS WebSocket
    v1/embeddings/routes.py          Forge Embed inference endpoint
    v1/models/routes.py              OpenAI-compatible model list/retrieval
    v1/responses/http.py             Responses HTTP mapping, resume, and SSE
    v1/responses/routes.py           ForgeEngine, planning, tool execution, and resume
  context/
    __init__.py                     Context package exports
    idempotency.py                  Thread-safe in-memory idempotency helper; unused by run
    limits.py                       ExecutionLimits, ExecutionBudget, ExecutionLimitError
    runtime.py                      Ambient runtime date/time context
    session.py                      Per-call in-memory message history
    state.py                        Per-run variables, resumable outputs, scratchpad, agent messages
  core/
    config.py                       Empty configuration module
    models/
      adapters/
        __init__.py                 Dispatcher exports
        base.py                     Abstract dispatcher, one-result stream, health stub
        canvas.py                   Canvas provider adapter
        text.py                     Text provider adapter
        media.py                    Media conversion provider
        voice.py                    Piper speech synthesis adapter
        stt.py                      faster-whisper speech-to-text adapter
      huggingface.py                Local Hub snapshot loader and model runtimes
      registry.py                   Model catalog with explicit runtime types
    attachments.py                  Attachment validation, routing, and extraction
    schemas/
      __init__.py                   Input/output schema exports
      input.py                      Orchestrator, attachment, history, Responses contracts
      output.py                     Static response, Thought, source/media, SSE contracts
    security/
      __init__.py                   Identity, RBAC, audit, and durability exports
      audit.py                      Append-only JSONL audit sink and redaction helper
      durability.py                 Tenant-subdirectory JSON checkpoint store
      identity.py                   Principal and required-identity helper
      rbac.py                       Role-to-permission authorization
      runtime.py                    ProductionIdentityResolver and anonymous-mode flag
  computer/
    config.py                       Code-owned Firecracker paths and resource limits
    hypervisor.py                   Firecracker API and microVM lifecycle
    instance.py                     Guest command and workspace file client
    guest.py                        Vsock guest agent installed in the prepared guest image
    manager.py                      Memory-aware autoscaling pool of run-scoped VM leases
    policy.py                       Command and workspace path guardrails
    workspace.py                    Local-tool path policy and temp cleanup
    policy.json                     Local-tool workspace roots/extensions/retention
  ochestrator/
    __init__.py                     OpenAI Agents SDK wrapper exports
    events.py                       SDK stream-event conversion
    runner.py                       SDK agent creation and Runner wrapper
  skills/
    loader.py                       Categorized, validated skill loader
    agents/<name>/SKILL.md          Specialist-agent instructions
    general/<name>/SKILL.md         Engine guidance
    tools/<name>/SKILL.md           Local-tool guidance
  synthesis/
    __init__.py                     Public synthesis exports
    aggregator.py                   Aggregate structured output items
    errors.py                       Failure policy for output synthesis
    formatter.py                    Responses/Chat Completions serializers
    normalizer.py                   Source/media normalization and filtering
    output.py                       Static response synthesis and SSE formatting
  tools/
    __init__.py                     Tool exports
    executor.py                     ToolResult, ToolExecutor, media normalization
    registry.py                     Local schema/handler registry
    definitions/
      __init__.py                   Tool definition package
      audio.py                      Audio probe
      calculator.py                 Calculator
      clock.py                      Current time
      data.py                       Data/SQL/reporting tools
      image.py                      Consolidated image operations
      search.py                     Web search
      spreadsheet.py                CSV read/write
      speak.py                       Local Piper text-to-speech tool
      text.py                        JSON extraction and extractive summarization
      transcribe.py                  Local faster-whisper speech-to-text tool
      video.py                      Consolidated video probe/frame/keyframe operations
tests/
  conftest.py                       Pytest setup
  test_eval.py                      Golden task/evaluation coverage
  test_forge.py                     Production/runtime behavior coverage
  test_idempotency.py               Idempotency helper coverage
  unit/test_data_tools.py           Data-tool tests
  unit/test_api_surface.py          Confirms versioned routes are mounted
  unit/test_local_tools.py           Local-tool tests
  unit/test_orchestrator_runner.py   SDK-wrapper tests
  unit/test_sandbox.py              Sandbox and cleanup tests
  unit/test_synthesis.py             Output and formatter tests
  unit/test_action_contract.py       Action ID uniqueness/catalog tests
  unit/test_tool_thoughts.py         Action lifecycle and legacy Thought tests
  smoke/test_end_to_end.py          Stub-provider in-process engine smoke test
  checkpoints/                      Test/checkpoint data; default store target
requirements.txt                    Runtime dependency ranges
Dockerfile                          Container build/start command
pyproject.toml                      Package metadata and Pyright configuration
README                              Project readme; not named README.md
TODO                                Development notes
logs/                               Default audit-log directory at runtime
```

**Current implementation paths:** the FastAPI app and lifespan are in
`src/orchestrator/api/__init__.py`; Chat Completions is mounted from
`src/orchestrator/api/v1/chat/completions/routes.py`; Responses HTTP binding
is in `src/orchestrator/api/v1/responses/http.py`; and the engine is in
`src/orchestrator/engine/engine.py`. Model catalog and gateway ownership are
under `src/orchestrator/inference/`.

### Dead and library-only inventory [PARTIAL]

“Reachable” here means called by the current FastAPI app or `ForgeEngine.run` path, not imported by tests.

| Path | Symbol/component | Reachable from engine/app? | Suggested action |
|---|---|---|---|
| `src/ochestrator/*` | SDK `OrchestrationRunner` and stream-event wrapper | No; custom engine uses `BaseAgent`/`AgentRegistry` | [DEAD / STALE] Round 3 decision: rename spelling if kept, otherwise remove after checking external imports |
| `src/orchestrator/api/health.py` | Empty health module | No | [DEAD / STALE] Implement health endpoints only if this app owns them; otherwise remove |
| Conversation title generation | Client-owned under D-013 | No title tool, route, request field, or response field | [REMOVED] |
| Approval, policy, ABAC, egress helpers | Removed by D-003 | No current runtime capability | [REMOVED] Reintroduce only with an authoritative boundary and end-to-end enforcement |
| `src/orchestrator/security/runtime.py` | `ProductionIdentityResolver` | Core backend-owned; not called by orchestrator app/run | [LIBRARY ONLY] Core backend resolves verified caller identity |
| `src/orchestrator/context/idempotency.py` | In-memory `IdempotencyStore` | No; request key not passed to run | [LIBRARY ONLY] Wire at the authenticated HTTP boundary or remove |

These are inventory recommendations, not deletion instructions. This table contains findings from the historical tree above; recheck every
path against the active package before acting on an inventory recommendation.

## 4. HTTP layer — actual vs intended [PARTIAL]

### Mounted routes [PARTIAL]

The app is `FastAPI(title="Forge Orchestrator", version="1.0.0")`. It mounts
six routers exposing seven HTTP operations and one WebSocket, and uses lifespan
to construct the engine and shut down the training exporter. Trusted upstream middleware
must supply the principal in `request.state`; the app does not accept identity
headers as proof.
Registered business operations are:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/responses` | Orchestration, external-tool suspension/resume, optional SSE |
| `POST` | `/v1/chat/completions` | Forge Text generation and SSE |
| `GET` | `/v1/models` | Forge model registry catalog |
| `GET` | `/v1/models/{modelId}` | Retrieve a Forge model by registry ID |
| `POST` | `/v1/embeddings` | Forge Embed inference |
| `POST` | `/v1/audio/transcriptions` | Authenticated multipart transcription using the shared `transcribe` tool |
| `POST` | `/v1/audio/speech` | Authenticated raw-audio speech response using the shared `speak` tool |
| `WebSocket` | `/v1/audio/sts` | Authenticated push-to-talk transcription → agent → speech session |

FastAPI also exposes its standard OpenAPI and documentation routes. The
previous `POST /v1/orchestrate` stub remains deleted and is not aliased.

### Mounted contract boundaries [PARTIAL]

`/v1/responses` binds `OrchestratorRequest`, maps trusted principal identity to
`ForgeEngine.run`/`resume`, and returns static responses or SSE. It currently
requires an injected/configured model provider for model-backed requests.
`/v1/chat/completions` accepts the standard `model`, `messages`, and `stream`
fields plus `max_tokens`/`max_completion_tokens`, `temperature`, `top_p`,
and `stop`. It invokes
the Forge Text definition through Hugging Face inference; no OpenAI endpoint
or API key is used. It returns `chat.completion` and SSE chunk object shapes.
The model response is generated before SSE chunks are emitted; this is
compatible framing, not incremental model-token streaming. Only one choice
(`n=1`) and text message content are supported. No title input or output field
is present.

`/v1/models` and `/v1/models/{modelId}` return the OpenAI model-object shape
(`id`, `object`, `created`, `owned_by`) backed by the Forge catalog. The
list endpoint wraps model objects as `{"object":"list","data":[...]}`.
`created` is currently `0` because the registry does not store model creation
timestamps; this is a schema-compatible placeholder, not the actual creation
time. `/v1/embeddings` calls the registered embedding model through
`HuggingFaceInference` and returns the standard list/data/index/embedding
shape. A Hub token is needed only for a private model repository.

### Draft vs. generated OpenAPI [PARTIAL]

The generated OpenAPI contains the HTTP operations, including the two batch
audio endpoints. WebSocket routes do not appear in OpenAPI. The committed
`docs/openapi.json` snapshot is regenerated from the live application after
HTTP schema changes.

### Middleware, identity and lifecycle [PARTIAL]

- All API routes require a trusted `request.state.principal`; orchestration and chat additionally enforce `orchestrate:run`. No identity claims are trusted from the body or headers.
- Authentication middleware is still an upstream responsibility and is not included in this package.
- Lifespan constructs `ForgeEngine` and shuts down its training exporter. Provider/client close-all wiring remains incomplete.
- `ProductionIdentityResolver` remains core-backend-owned; it is not app authentication middleware.

## 5. Request contract (schemas) [PARTIAL]

Internal schemas follow the project's camelCase convention. Compatibility
routes also accept OpenAI's required snake_case spellings where applicable
(for example `max_tokens`, `max_completion_tokens`, and `top_p`).
`OrchestratorRequest` is bound to `/v1/responses`.
Public JSON field names are camelCase except `call_id` and
`previous_response_id`; see D-006 and the
[wire contract](../references/wire-contract.md).

### `OrchestratorRequest` [PARTIAL]

| Field (wire alias) | Type | Required/default | Validation | Current engine use |
|---|---|---|---|---|
| `messages` | message/output item list | Required; new requests end with a user message; resume requests contain one function output | Messages contain role/content/attachments; output items use `type=function_call_output`, `call_id`, and `output` | Conversation context or caller result for resume |
| `stream` | `bool` | `False` | Pydantic boolean parsing | Chooses static vs returned stream generator |
| `reasoning.effort` | `low`, `medium`, `high`, `xhigh` | `medium` | Validated enum | Maps to engine `fast`, `auto`, or `expert`; `xhigh` maps to `expert` |
| `tools` | caller-owned function schema list | Empty | Function name constrained; parameters retained as JSON Schema | Planner schemas only; topology is derived internally |
| `previous_response_id` | optional run ID | `None` | Required with exactly one function output message | Loads the tenant/user-bound suspended checkpoint |
| `metadata` | `dict[str, Any]` | Empty | `trainingExport`, when present, must be boolean | Controls opt-in training export |

Client-provided session IDs, execution topology, separate function-output
lists, title-generation controls, and tool arguments are not part of this
public request schema. The engine creates its session ID internally.

### Nested input schemas [UNWIRED]

| Schema | Field | Type/default | Validation/notes |
|---|---|---|---|
| `AttachmentPayload` | `fileId` | `str`, required | Length 1–200 |
| | `fileName` | `str`, required | Length 1–255 |
| | `mimeType` | `str`, required | Length 1–255; supported signatures are checked against actual bytes |
| | `fileData` | `str`, required | Strict base64, decoded-size capped, and optionally checksum-verified |
| | `attachmentType` | `AttachmentType`, `unknown` | Derived from `mimeType`; caller values are not trusted |
| | `fileSizeBytes` | `Optional[int]`, `None` | Must be `>= 0` |
| | `checksumSha256` | `Optional[str]`, `None` | 64 hexadecimal characters |
| | `metadata` | `dict[str, Any]`, empty | No content validation |
| `HistoryMessage` | `messageId` | `Optional[str]`, `None` | Optional persisted ID; no persistence here |
| | `role` | Literal system/user/assistant, required | Tool role is not accepted by this schema |
| | `content` | `str`, required | Maximum 8,000 characters |
| | `createdAt` | `Optional[datetime]`, `None` | Parsed datetime |
| | `attachments` | list of `AttachmentPayload`, empty | Only attachment names enter history prompts; base64 bytes are not retained |

### Responses-style schemas [PARTIAL]

The older OpenAI-shaped `ResponsesRequest`, `ResponsesInputContent`,
`ResponsesInputMessage`, and `ResponsesFunctionCallOutput` models remain
library-only. The mounted endpoint currently accepts the orchestration
`OrchestratorRequest` contract above. Input media is base64-only; callers fetch
online assets before submitting them. Tool results that contain media URLs are
converted to base64 by `ToolExecutor` before model or response use.

### Output and stream schemas [PARTIAL]

| Schema | Contract | Binding/observed behavior |
|---|---|---|
| `UnifiedOrchestratorResponse` | `runId`, `status`, optional `functionCalls`, ordered `events`, ordered `content` blocks, `sources`, `metadata` | Returned by static `/v1/responses`; title, `mediaAssets`, and `thoughts`/`actions` are not top-level fields |
| `ContentBlock` | `type` is `text`, `image`, `video`, `audio`, or `file`; non-text blocks contain bounded base64 `mediaData` and `mimeType` | `content` order is significant; media URLs are not emitted |
| `events` | Ordered Thought, Action, and RunStatus records | Replaces separate top-level reasoning/action lists; stream `complete.data.events` matches the collected timeline |
| `Thought` | ID regex `^T[A-Z0-9]{5}$`; reasoning/progress only; non-empty message; status started/processing/completed; data object | Thought IDs are emitted beside reasoning/progress code; temporary legacy tool Thoughts have `data.deprecated: true`. |
| `ActionRecord` | ID regex `^A[A-Z0-9]{5}$`; action type/name, lifecycle status, message, optional metadata/error | Tool/integration/data execution record; no raw arguments or results |
| `RunStatus` | started/planned/completed/failed/cancelled/requires_action, optional timing/counts/reason | Machine-readable run lifecycle |
| `FunctionCall` | `type=function_call`, `call_id`, `name`, JSON-encoded arguments | Returned in requires-action response |
| `SourceReference` | Required title/url; optional snippet; source type web/document/integration/other; metadata | Static graph's sources remain empty; stream graph emits no source event |
| `StreamEvent` | Discriminated union: `event`, `textChunk`, `function_call`, `media`, or `complete`; run ID; sequence >= 1; data typed per packet | `event.data` is `OrchestratorEvent`; timeline items are not separate SSE packet types |

Effort comes from `reasoning.effort`; topology is derived from the presence of
caller-owned `tools` and is not client-controlled. A `trajectoryExport=true`
request is rejected for external-tool runs because those runs are interactive.

`ForgeEngine.run` additionally accepts external function schemas, topology,
effort mode, and per-request training export. `previous_response_id` and
`function_call_outputs` are handled by `ForgeEngine.resume`. `HistoryMessage.content`
has `Field(..., max_length=8000)` (`src/orchestrator/schemas/input.py`,
`HistoryMessage`).

## 6. Engine construction & dependency injection [PARTIAL]

### Constructor [IMPLEMENTED]

`ForgeEngine.__init__(text_dispatcher=None, dispatcher_registry=None, execution_limits=None, audit_log=None, checkpoint_store=None)`:

| Parameter | Default | Effect |
|---|---|---|
| `text_dispatcher` | `None` | Stored; passed to classifier/planner/refiner and six agents |
| `dispatcher_registry` | `None` | Copied into a new mapping; missing `text`, `image`, `audio` keys receive defaults |
| `execution_limits` | `None` | Uses `ExecutionLimits()` if absent |
| `audit_log` | `None` | Uses `AuditLog()` if absent; creates `logs/` directory |
| `checkpoint_store` | `None` | Uses `CheckpointStore()` if absent; creates the default checkpoint directory |
| training exporter | N/A | Reads opt-in export/HF environment configuration; its worker starts on first record |

Construction also creates an `AgentRegistry` with six custom agents, `ToolExecutor`, the tool registry, `IntentClassifier`, `ExecutionPlanner`, and `PromptRefiner`. Default dispatchers are `TextDispatcher()` (provider absent), `CanvasDispatcher()` (provider absent), and `VoiceDispatcher()` (provider absent).

### Default constructor and registry IDs [IMPLEMENTED]

`ToolExecutor()` calls `create_default_registry()`, which registers local tools
only. Per D-001, the registry stores schemas and handlers; it does not read or
require `THOUGHT_IDS`/`getThoughtIds()`. Local Action descriptors are attached
to handlers. Default engine construction is independent of Action metadata.

### Provider and client lifecycle [PARTIAL]

- API lifespan constructs `ForgeEngine` but does not inject a configured provider.
- Dispatchers are wrappers, not configured provider clients; no default provider is discoverable in the constructor.
- The tool registry contains only local definitions and does not create remote service clients.
- `MediaConverter` owns its optional HTTP client; provider and media clients are not yet closed by the application lifespan.
- App lifespan shuts down the training exporter. It does not yet close provider or media clients.

### Current lifespan behavior [PARTIAL]

`src/orchestrator/api/__init__.py` creates the engine during lifespan and assigns it to
`app.state.engine`. On shutdown it awaits `engine.trainingExporter.shutdown()`
so any queued records are flushed. Provider factory/settings and public
tool-registry close-all remain unimplemented; do not treat unconfigured
dispatchers as production-ready.

See lifecycle gaps G-003 and G-026.

### Import-time work [PARTIAL]

| Module | Import-time work found | Deferred work |
|---|---|---|
| `src/orchestrator/api/__init__.py` | Creates FastAPI and imports the versioned routers | Lifespan constructs the engine and shuts down the exporter |
| `src/orchestrator/api/v1/responses/routes.py` | Defines engine/helpers; no skill-file read | `_load_skill()` reads when classification/refinement/title helpers execute |
| `computer/workspace.py` | Defines local-tool path-policy functions; no policy JSON read or environment lookup | `_sandboxRoot()` reads `FORGE_SANDBOX_ROOT`; `_loadPolicy()` reads `policy.json` when a safe path/cleanup call occurs |
| `src/orchestrator/security/runtime.py` | Defines resolver class | `FORGE_ALLOW_ANONYMOUS` is read by resolver construction |
| `src/orchestrator/security/audit.py`, `src/orchestrator/security/durability.py` | No directory creation on import | Constructors create log/checkpoint directories |
| `src/orchestrator/tools/definitions/` / `src/orchestrator/tools/executor.py` | No tool handlers or HTTP clients are created on import | The engine creates its shared media converter; handlers execute only when selected |

A cold subprocess running `from orchestrator.engine.engine import ForgeEngine` exited successfully in about 13.34 seconds on this environment; this wall time includes interpreter startup and transitive imports, so it is not an isolated module-import benchmark. The app module imports router definitions; engine/client construction remains deferred to ASGI lifespan.

## 7. End-to-end request lifecycle (`ForgeEngine.run` and `resume`) [PARTIAL]

The HTTP route supplies an authenticated principal to the engine. Direct
library callers may also pass a principal or use the legacy user/tenant
arguments.

### 7.1 Identity and authorization [IMPLEMENTED]

Each call creates a random `run_<8 hex>` ID and an `ExecutionBudget`. A supplied `Principal` is used directly. Otherwise `user_id` and `tenant_id` are required and a principal with role `operator` is created. `require_authorization` checks `orchestrate:run`. RBAC also rejects a resource tenant different from the principal tenant, but the current run calls it without a separate resource tenant, so the equality check is effectively principal-self consistency.

### 7.2 Temporary files, audit, context [PARTIAL]

`cleanupTmp()` runs before session/state creation. Removed files produce `sandbox.tmp.cleaned`; cleanup exceptions produce `sandbox.tmp.cleanup_failed` with exception type. Both audit error handling and cleanup error handling are broad and best-effort; audit failure during cleanup failure is swallowed.

The run creates ambient date/time context, a new `SessionManager(sessionId, history)`, and `ExecutionState`. It stores user/tenant/roles and raw `toolArguments` in state, appends the user prompt to the transient history, and later appends static assistant output. State and history are per-call and in memory; no cross-call session lookup or database persistence occurs. Stream mode does not append the final assistant message to `SessionManager`.

### 7.3 Attachment classification [PARTIAL]

Mappings are converted to `AttachmentPayload`; each current-turn attachment
provides base64 bytes only. Remote attachment URLs are rejected and must be
fetched by the caller before submission. Media is bounded by
the code-owned `MAX_ATTACHMENT_BYTES` limit (10 MiB) and checked for declared
size/checksum and recognized MIME signatures. History attachments remain
base64-only. The dispatcher extracts image OCR and supported text content;
unsupported formats return an explicit unsupported result. Extracted
attachment content is injected into classifier and refiner prompts, capped at
4,000 characters per attachment and 12,000 total. Image attachments select the
vision capability. Image bytes are passed only to a configured `vision`
dispatcher implementing `analyze_image(prompt=..., system_prompt=...,
images=...)`; without one, image analysis fails explicitly. Inline image bytes
and extracted attachment content are excluded from checkpoint exports.

### 7.4 Intent classification and prompt refinement [PARTIAL]

`IntentClassifier` reads cached `src/orchestrator/skills/classifier/SKILL.md`; with a provider it tries structured output, then text/JSON output. Without a provider it returns deterministic text/chat intent. Invalid JSON or invalid intent shape raises `ValueError`; an async return from this synchronous interface raises `RuntimeError`.

`PromptRefiner` selects a profile based on capability/modality and reads `src/orchestrator/skills/refiner/SKILL.md`. It uses structured/text provider output when available; malformed refinement output falls back to a deterministic prompt. An awaitable result from its sync interface raises rather than being awaited.

Both helpers receive extracted attachment content and the last ten conversation
messages. History is included as `## Conversation so far`, capped at 2,000
characters per message and 8,000 characters total. Historical attachment bytes
are discarded; only attachment names may appear in the history block. The
planner receives the original request rather than extracted attachment text.

### 7.5 Planning and dependency validation [PARTIAL]

`ExecutionPlanner.create_plan()` creates a one-step plan when there is no multi-step, tool, or multi-modality requirement. Otherwise it requires a text planner and sends the intent plus registered tool schemas. It validates that the plan is non-empty, tool names are registered, and tool-required intent includes a tool. `_orderedSteps()` orders ready steps and raises `ExecutionLimitError` when dependencies form a cycle.

`ExecutionPlan.is_sequential` does not switch execution strategy. Both static and stream loops process steps serially. Dependency IDs that do not refer to a plan step also prevent a step becoming ready and surface as the cycle error.

After planning, a `planned` checkpoint is saved and `run.planned` is audited. Failures before this point do not create an error checkpoint or `run.failed` audit record.

### 7.6 Execution: tools, agents, dispatch [PARTIAL]

- Tool steps invoke `_executeToolCall(toolName, state)`. The tool name comes from the planner; the arguments come from the caller's `toolArguments[toolName]`. Missing arguments default to `{}`. `ToolExecutor` validates each object against the registered JSON Schema before dispatch; validation failures return a typed `ToolResult` with `code=INVALID_ARGUMENTS` and a redacted `action.invalid_arguments` audit event.
- Non-tool steps use `AgentRegistry.resolve(capability, modality)`. It scores exact normalized capability match at 100 and modality-in-capabilities at 20, and picks the highest score. There is no tie-breaking by explicit priority beyond dictionary insertion order.
- The selected `BaseAgent` builds a prompt from its system prompt, the instruction, and scratchpad entries ending `.result`. It retries dispatch up to two attempts by default, with a short sleep between failures, then raises `AgentExecutionError`.
- If no agent matches, `_dispatchStep` looks up the modality dispatcher and calls `generate`; absent dispatchers/methods raise `RuntimeError`.
- Agent messages/handoffs are appended to state; the engine does not consume handoff messages to schedule another agent. `AgentRegistry.collaborate()` itself adds a coordinator result message.
- Local tool calls execute in the same process. Caller-owned external tools
  suspend the run and are executed only by the caller.

### 7.7 Budgets, evaluator and failures [PARTIAL]

Default `ExecutionLimits`: 10 steps, 20 tool calls, 12 iterations, 300 seconds, 100,000 estimated tokens.

| Limit/behavior | Enforced in engine? | Notes |
|---|---|---|
| Steps | Yes | `begin_action()` checks before each plan step |
| Iterations | Yes | Also checked by `begin_action()` |
| Overall elapsed runtime | At step boundaries | `begin_action()` checks elapsed time; a long step has a separate timeout |
| Per-step timeout | Partial | `asyncio.wait_for()` wraps agent/dispatcher execution; timeout is set to the full configured runtime, not remaining run time |
| Estimated tokens | Approximation | Word/character heuristic on prompts/output; not provider token usage |
| Repeated actions | Yes, for last three fingerprints | Separate tool fingerprints are not added through current engine path |
| `max_tool_calls` | **Yes** | Internal tool calls are counted before dispatch; a breach fails the run with `terminationReason=tool_call_limit` |
| Duplicate tool fingerprint | **Yes** | A repeated `(toolName, argumentsHash)` is stopped after three calls |
| External tool calls | Excluded | Caller-owned function calls suspend for caller execution and do not consume the internal tool budget |
| Tool-call timeout | Adapter-specific only | `ToolExecutor` itself imposes no separate handler timeout. |

`ExecutionEvaluator` runs every third non-tool iteration. It asks a provider for structured decisions when available; broad `except Exception` silently falls back. Deterministic fallback checks repeated output fingerprints and can use previous scores, but engine callers pass no score history, so score-plateau detection is unreachable from the engine. A tool-only step `continue`s before evaluator logic.

Exceptions are not translated by an HTTP layer because none exists. Identity/RBAC, invalid plan, cycle, missing dispatcher/provider, JSON parse, and most tool exceptions can propagate to a direct caller. Static/stream graph catches `ExecutionLimitError` at action boundaries; per-step timeouts are converted to that error. A failed `ToolResult` sets terminal status to `failed` and breaks the tool list, but may leave primary content empty. External tool failures are returned by the caller through the resume contract.

Broad catches currently present include cleanup/audit best effort and evaluator fallback. There is no global run failure recorder. `asyncio.CancelledError` is not explicitly handled; on supported Python versions it derives from `BaseException`, so ordinary `except Exception` blocks do not swallow cancellation. No explicit `finally` closes tools or writes a cancellation checkpoint.

### Error taxonomy [PARTIAL]

There is no HTTP exception mapper. Direct static callers see uncaught exceptions from `run()`; stream callers may see them only while consuming the returned async generator.

| Exception | Source and trigger | Engine handling | What caller sees |
|---|---|---|---|
| `ExecutionLimitError` | `src/orchestrator/context/limits.py`; step/iteration/time/token/repeat limits and dependency cycles (`_orderedSteps`) | Caught at `begin_action()` boundaries; other raises such as token accounting or `_orderedSteps()` can escape | Status/termination for caught boundaries; otherwise exception propagates, including through stream iteration |
| `AgentExecutionError` | `src/orchestrator/agents/base.py`; missing/invalid dispatcher result or retries exhausted | Agent wraps the final failure; run graph has no general catch | Propagates to static caller or stream iterator |
| `ValueError` | Classifier/planner input or plan failures; handler-owned descriptor errors | Constructor/engine have no global catch; malformed `PromptRefiner` output is handled by its deterministic fallback | Construction or unhandled run error propagates; no HTTP mapping |
| `RuntimeError` | Classifier/refiner sync-interface awaitable misuse; `_dispatchStep` missing dispatcher/method | No outer catch (agent invocation may wrap it after retry) | Propagates, or appears as `AgentExecutionError` when raised within agent retries |
| `KeyError` | `src/orchestrator/tools/registry.py:ToolRegistry.execute` for unknown name; adapters may index required arguments | No engine-level catch | Propagates to direct caller/stream consumer |
| `TypeError` | `src/orchestrator/tools/executor.py:ToolExecutor.executeAsync` when arguments are not a mapping | No engine-level catch | Propagates to direct caller/stream consumer |
| `asyncio.TimeoutError` | `asyncio.wait_for()` in static/stream graph | Graph catches wait timeout then calls `budget._stop()`, which raises `ExecutionLimitError` | Normally `ExecutionLimitError` |
| `asyncio.CancelledError` | Task cancellation during awaited work | No explicit catch or `finally`; not swallowed by `except Exception` on supported Python | Cancellation propagates; no cancellation audit/checkpoint |
| `IdentityContextError` / `PermissionError` | `src/orchestrator/security/identity.py`; missing IDs or denied RBAC permission | No run-level translation | Propagates to direct caller |

`src/orchestrator/api/v1/responses/routes.py` has broad `except Exception` handling in cleanup/audit and evaluator fallback paths; some use silent fallback/ignore behavior. Other broad catches exist in agent retry and selected adapters/tools. No `except BaseException` or bare `except:` was found by source scan. These local catches do not form a consistent error contract.

### 7.8 Output, stream, checkpoint and audit [PARTIAL]

> **Round 2 correction:** Source availability was described generally; exact source shows `_executeGraphStatic()` initializes `sources = []` with no append. The stream graph emits `content` chunks. Those are separate confirmed behaviors (`src/orchestrator/api/v1/responses/routes.py`, `_executeGraphStatic`, `_executeGraphStream`).

Static mode collects text, thoughts and media, appends assistant text to transient history, saves a `completed` checkpoint, and writes `run.completed`. Conversation titles are not generated or included in the response. `_executeGraphStatic()` sets `sources = []` and does not append to that list; no static source is produced (`src/orchestrator/api/v1/responses/routes.py`, `_executeGraphStatic`).

Stream mode returns an async generator after the planned checkpoint/audit. Text is generated as a complete step result first, then split on whitespace with a 20ms sleep between chunks; it is not provider token streaming. The graph yields text data as `{"content": chunk + " "}` (`_executeGraphStream`), with cancellation propagated by `_executeGraphStreamWithCancellation`. Stream events can carry `thought`, `textChunk`, and terminal `complete`; media/source are intermediate generator events, not valid public `StreamEvent` types. The current graph emits media but no source. The stream branch does not save a completed checkpoint or write `run.completed`.

The checkpoint/audit branch is explicit in `ForgeEngine.run`: both modes first save `"planned"` and record `"run.planned"`; only the static `else` block saves `"completed"` and records `"run.completed"`. The returned stream generator has no such terminal write. (`src/orchestrator/api/v1/responses/routes.py`, `ForgeEngine.run`)

| Static branch | Stream branch |
|---|---|
| Saves `planned`, then executes and saves `completed`; records `run.completed` | Saves `planned`, then returns `OutputSynthesizer.synthesizeStream(...)`; no completed save or `run.completed` |

`OutputSynthesizer` normalizes/deduplicates sources and media, redacts selected secret-like dictionary keys and bearer strings, applies a failure policy, and formats the final `complete` event. Its separate Responses/Chat Completions serialization helpers are not used by the direct Forge Text route, which maps the provider result to the OpenAI-compatible contract itself. The stream sends no SSE event for internal `source` records; those are collected into the final response only.

### Shared state and concurrency [PARTIAL]

Each `run()` has its own budget/state/session. The engine's local registry,
dispatcher wrappers/providers, `MediaConverter`, `AuditLog`, and
`CheckpointStore` are shared if the engine is reused.

| Shared object | Mutated post-init? | Locked/serialized? | Risk tag | Two-run test that would prove safety |
|---|---|---|---|---|
| `AgentRegistry` / agents | Registry normally read-only; provider internals may mutate | No registry/agent lock | [RISK] provider-specific state may race | Run two plans through the same agent concurrently; confirm isolated prompts/results and state |
| `ToolRegistry` | Registration mutates maps during construction; dispatch reads them afterwards | No lock; no runtime re-registration in normal engine path | [PARTIAL] construction must finish before serving | Concurrently dispatch distinct and same-name tools; verify stable handler and Thought-ID resolution |
| Dispatchers/providers | Engine does not mutate wrappers post-init; provider behavior is implementation-specific | No dispatcher-level serialization | [RISK] depends on provider concurrency contract | Concurrent calls do not cross-contaminate prompts/results and respect provider limits |
| `AuditLog` | Appends file records | No thread/process lock; one append handle per record | [RISK] concurrent/multi-process line integrity unproven | Parallel static/stream runs yield intact JSON records, one per line |
| `CheckpointStore` | Filesystem changes on save; store configuration stays fixed | No lock or atomic write; random run IDs reduce same-file collision | [RISK] concurrent writes and path containment unproven | Parallel saves/loads produce complete JSON isolated by tenant and run |

`AuditLog.record()` (`src/orchestrator/security/audit.py`) contains no
synchronization. The app must not claim safe singleton-engine concurrency
until these tests pass.

## 8. Agents [PARTIAL]

| Specialist | Declared capability examples | Modalities | Prompt source | Retry behavior |
|---|---|---|---|---|
| Research | research, search, analysis, fact checking, web research | No modality-specific model; shared injected text dispatcher | Loaded lazily from `src/orchestrator/skills/agents/research/SKILL.md` through `BaseAgent.system_prompt` | `BaseAgent` default 2 attempts |
| Coding | coding, code, review, debugging, testing, implementation | Shared injected text dispatcher | Loaded lazily from `src/orchestrator/skills/agents/coding/SKILL.md` | 2 attempts |
| Document | document, PDF, invoice, table, structured RAG | Shared injected text dispatcher | Loaded lazily from `src/orchestrator/skills/agents/document/SKILL.md` | 2 attempts |
| Data | data, analytics, SQL, pandas, reporting, spreadsheet | Shared injected text dispatcher | Loaded lazily from `src/orchestrator/skills/agents/data/SKILL.md` | 2 attempts |
| Vision | vision, image/video understanding, OCR, object detection | Optional injected `vision` dispatcher with `analyze_image`; image bytes require a multimodal dispatcher | Loaded lazily from `src/orchestrator/skills/agents/vision/SKILL.md` | 2 attempts for text dispatch |
| Media | image/video generation, composition, rendering | Shared injected text dispatcher; no Canvas/Video model binding | Loaded lazily from `src/orchestrator/skills/agents/media/SKILL.md` | 2 attempts |

Capability matching normalizes underscores/case, adds 100 for exact capability and 20 if the modality itself is in agent capabilities, then selects the maximum. For current-turn image attachments, normalized base64 bytes are supplied to the vision agent; the configured vision dispatcher must implement `analyze_image(prompt=..., system_prompt=..., images=...)`.

**Messages and handoffs [LIBRARY ONLY]:** custom agents record result/context/review/handoff messages in `ExecutionState`; no scheduler reads them. Handoff metadata explicitly starts `accepted: false`.

**OpenAI Agents SDK wrapper [LIBRARY ONLY]:** `src/ochestrator/runner.py` and `events.py` construct SDK agents and translate streamed text deltas. `ForgeEngine` uses custom `BaseAgent`/`AgentRegistry`, not `OrchestrationRunner`. Some specialist files import SDK builder helpers, but the default custom engine does not call them. The package path is misspelled `ochestrator`; retain/rename only after deciding whether this separate path is still intended.

## 9. Tools [IMPLEMENTED]

`DEFAULT_MODULES` registers 18 local tool names. Every tool requires one of
the operation values below; the same values appear in its skill and the
Action ID catalog.

| Tool call shape | Operations and status |
|---|---|
| `audio(operation=...)` | `probe`, `trim`, `convert` implemented |
| `calculate(operation=...)` | `evaluate` implemented |
| `clock(operation=...)` | `now`, `convert` implemented |
| `computer(operation=...)` | `execute`, `read_file`, `write_file` implemented in disposable Firecracker microVMs |
| `data(operation=...)` | `table`, `sql`, `profile`, `join`, `report`, `chart` implemented |
| `extract(operation=...)` | `json`, `xml`, `yaml`, `csv` implemented |
| `fetch(operation=...)` | `url`, `pdf`, `json` implemented with allowlisted HTTPS retrieval |
| `generate(operation=...)` | `image`, `audio` implemented through local Forge models |
| `image(operation=...)` | `info`, `resize`, `ocr`, `generate` implemented |
| `pdf(operation=...)` | `text` implemented |
| `search(operation=...)` | `web`, `image`, `news` implemented through the search provider |
| `sheet(operation=...)` | `read`, `write`, `info` implemented |
| `speak(operation=...)` | `text` implemented |
| `summarize(operation=...)` | `text`, `url` implemented; URL access is allowlist-gated |
| `transcribe(operation=...)` | `audio` implemented |
| `translate(operation=...)` | `text`, `document` implemented through the configured local Forge Text model |
| `video(operation=...)` | `probe`, `sample`, `keyframe` implemented |
| `weather(operation=...)` | `current`, `forecast` implemented through the tool-local Open-Meteo client |

No registered operation returns `NOT_IMPLEMENTED`. Provider-backed operations
return explicit provider/configuration errors when a deployment dependency is
unavailable. The `computer` tool requires Linux/KVM and a prepared guest
image; it returns `COMPUTER_UNAVAILABLE` rather than running commands on the
host when those dependencies are missing. The guest has no network interface,
uses a read-only root disk, mounts `/workspace` as temporary storage, and
executes commands as an unprivileged user. The pool maintains five warm
instances and scales on demand up to a code-owned limit of 200, further
bounded by detected host/cgroup memory. Same-run operations are serialized
and acquisition waits up to 30 seconds at capacity. Snapshot cloning is not
enabled because the runtime has no safe guest-side entropy/identity-reset
protocol. These defaults are code-owned in
`orchestrator/computer/config.py`, not environment variables. Local file
tools retain their path policy in
`computer/workspace.py`; it is separate from the isolated guest runtime.
The former aggregate `future_tools.py` was deleted;
each active tool has its own definition module and exactly one matching skill
folder with one `SKILL.md`. Host-process code/shell execution, interactive
browser control, image analysis/detection, video generation, and PDF
table/image extraction remain unavailable. `fetch`, URL summarization, and
weather are explicit network integrations with bounded behavior; see D-021
and D-026.
`test_one_skill_per_tool.py` enforces parity;
`test_tool_operations_audit.py` checks the required operation field and
skill/schema agreement and implemented statuses. See
[D-009](../decisions/D-009-one-word-tool-contract.md),
[D-019](../decisions/D-019-one-tool-per-domain-one-skill.md), and
[D-020](../decisions/D-020-uniform-operation-field.md) and
[D-021](../decisions/D-021-no-registered-placeholder-operations.md).
The built-in `todo` and `memory` tools and their SQLite state store were
removed under [D-022](../decisions/D-022-no-stateful-tools.md); callers that
need durable state provide external tools under D-004. The `data` tool's
read-only access to caller-provided SQLite files is not tool-owned storage.
Tool-specific non-model integrations stay with their tool definition.
Inference modality facades and backends stay under
`src/orchestrator/inference/` (D-023, D-024).

Speech handlers use the local faster-whisper and Piper dispatchers through
private dependencies injected by `ToolExecutor`; dispatchers are never
model-visible tool arguments. Batch HTTP endpoints and the STS pipeline reuse
the same handlers. The audio route shape is compatible with OpenAI clients,
but no speech request is sent to OpenAI. Piper currently supports only the
configured voice and WAV/PCM output.

External services are caller-owned tool schemas under D-004. They suspend
with `call_id` and resume through a `function_call_output` message. The
orchestrator does not hold their credentials, ship their adapters, or write
their skills.

`ToolExecutor` parses function arguments and validates them against the
registered JSON Schema before dispatch. Invalid arguments return a typed
`ToolResult` with `code=INVALID_ARGUMENTS`; the audit event records the tool
name and schema path, not raw arguments. See
[D-006](../decisions/D-006-wire-camelcase-and-validation.md).

Filesystem-facing local handlers enforce paths using `safePath()` in
`src/orchestrator/computer/workspace.py`. Media URLs produced by local tools are converted
to bounded base64 before they can reach the model or response. Citation URLs
are kept separately in `SourceReference`.

## 10. Inference subsystem [IMPLEMENTED]

### Dispatchers [PARTIAL]

| Dispatcher | Registry key | Provider default | Behavior |
|---|---|---|---|
| `TextDispatcher` | `text` | None | Calls provider `generate_text`/`generate`/callable; validates non-empty text |
| `CanvasDispatcher` | `image` | None | Calls `generate_image`/`generate`/callable; rejects `None` |
| `VoiceDispatcher` | `audio` | Local Piper | Loads the configured ONNX voice and synthesizes WAV or raw PCM |
| `SttDispatcher` | `stt` | Local faster-whisper | Loads the configured Whisper model and returns transcript/segment data |

`ToolExecutor` privately injects `audio` and `stt` dispatchers into their matching
tool handlers after validating model-supplied arguments against the tool
schema. The app lifespan injects gateway-backed modality facades; a standalone
`ForgeEngine` can receive custom dispatchers. The local model libraries load
lazily on first inference, and the gateway owns backend caching and shutdown.

### Model catalog, sources, and backends [IMPLEMENTED]

`src/orchestrator/inference/registry.py` lists model IDs, capabilities,
default artifact locators, and backends:

| Key / model ID | Catalog capability summary | Engine dispatcher |
|---|---|---|---|
| `text` / Text | Chat, reasoning, code, tool use | `Qwen/Qwen2.5-0.5B-Instruct` / Transformers; chat route wired |
| `image` / Canvas | Text-to-image, image editing | `stabilityai/sd-turbo` / Diffusers |
| `audio` / Voice | Text-to-speech | `rhasspy/piper-voices` / Piper; selected voice files only |
| `transcription` / Speech | Speech-to-text | `Systran/faster-whisper-small` / faster-whisper |
| `video` / Motion | Video generation/editing/composition | `zai-org/CogVideoX-2b` / Diffusers |
| `vision` / Vision | Image/video perception, OCR, spatial extraction | `HuggingFaceTB/SmolVLM-256M-Instruct` / Transformers vision-to-sequence |
| `document` / Ledger | PDF/invoice/table extraction, structured RAG | `Qwen/Qwen2.5-0.5B-Instruct` / Transformers |
| `data` / Analyst | SQL, pandas, analytics, reporting | `Qwen/Qwen2.5-Coder-0.5B-Instruct` / Transformers |
| `embedding` / Embed | Text embeddings | `sentence-transformers/all-MiniLM-L6-v2`; `/v1/embeddings` wired |

`InferenceGateway` resolves each configured locator through its source, then
constructs the selected backend with the local artifact path. Backends run the
declared runtime locally; gateway instances are cached and closed with the
application lifespan. `HF_TOKEN` is used by `HuggingFaceSource` for private or
gated Hub downloads and by `HuggingFaceSync` when optional uploads are
configured. Model source and backend settings can override registry defaults.
Optional backends that are not configured fail explicitly at resolution.

The catalog endpoint exposes registry entries as OpenAI-compatible model
objects. Catalog presence is metadata, not proof that model weights are
available or that each runtime supports a public endpoint. Chat Completions,
embeddings, transcription, and speech synthesis load local runtimes.
`video`, `vision`, `document`, and `data` do not yet have public inference
routes.

 ## 11. Security, identity, persistence [PARTIAL]

 ### RBAC and identity [IMPLEMENTED / UNWIRED]

 `Principal` contains user ID, tenant ID, roles, groups, and string attributes.
 The `operator` and `integration_admin` roles grant `orchestrate:run`;
 `require_authorization` enforces that permission at `ForgeEngine.run`.
 Unknown roles grant nothing. No HTTP route currently supplies authenticated
 claims to the engine.

 `ProductionIdentityResolver` remains available for the core backend's
 authenticated caller boundary. It does not verify tokens and is not an
 orchestrator middleware or tool-policy mechanism.

 ### Removed policy scaffolding [DECIDED]

 Per [D-003](../decisions/D-003-remove-unwired-policy-scaffolding.md),
 `ApprovalStore`, `PolicyEngine`, ABAC, egress-policy helpers, their
 approval-specific RBAC permission, and their helper tests have been removed.
 This orchestrator does not provide approval gating, attribute-based
 authorization, or outbound-host allowlisting. External write tools remain
 callable when invoked with valid credentials; these controls must be designed
 and enforced at the authoritative core-backend boundary if required.

 Per [D-002](../decisions/D-002-separate-thoughts-from-actions.md), Action
 metadata is redacted through the existing audit redaction helper before it is
 included in Action stream/static records. Raw tool arguments, results, and
 exception messages are not emitted in Action payloads.

### Audit and redaction [PARTIAL]

`AuditLog` appends JSONL to `logs/forge-audit.jsonl` by default, relative to process working directory. Each record has event, run/tenant/user IDs, UTC timestamp, and details. It recursively redacts a fixed set of secret-like keys and bearer tokens in strings. It does not rotate, expire, or lock files, and it is not a complete PII scrubber.

Events emitted by the run path:

| Event | When/details |
|---|---|
| `sandbox.tmp.cleaned` | Only if cleanup removes one or more files; includes count |
| `sandbox.tmp.cleanup_failed` | Cleanup fails; includes exception type only, if audit succeeds |
| `run.planned` | After plan checkpoint; includes planned step count |
| `run.completed` | After successful static graph return; includes executed steps |

Run `started`, `planned`, `completed`, and `failed` states are emitted as stream
Status events, but failed/cancelled/stream terminal outcomes are not recorded
as audit events. Approval-related audit events do not exist.

Observed, redacted `run.planned` line from a successful in-process smoke run (identifiers/time redacted; shape and `steps` value retained):

```json
{"details":{"steps":1},"event":"run.planned","runId":"run_[REDACTED]","tenantId":"[REDACTED]","timestamp":"[TIMESTAMP]","userId":"[REDACTED]"}
```

### Checkpoints and persistence [PARTIAL]

Default path is `data/checkpoints/<tenant_id>/<run_id>.<checkpoint>.json`;
`FORGE_CHECKPOINT_ROOT` overrides it. Writes use same-directory temporary
files and atomic replace. Tenant/run/checkpoint path components are validated,
resolved paths are constrained under the configured root and tenant directory,
and checkpoints expire after 30 days by default
(`FORGE_CHECKPOINT_RETENTION_DAYS`). Suspended checkpoints include the plan,
pending `call_id`, arguments, completed tool/step results, identity, and
resume-response cache. `exportState()` includes run ID, all state variables
and step outputs; treat checkpoint data as sensitive. Files are plaintext:
production storage must provide access control, encryption, backup, and
persistent-volume guarantees.

Historical Round 2 example captured from a simple static `ForgeEngine.run()` with a test-only empty tool registry substituted to bypass the then-present Canva construction blocker; identifiers, prompts, outputs, and time values are redacted:

```json
{
  "runId": "run_[REDACTED]",
  "stepOutputs": {
    "1": "[model output]"
  },
  "variables": {
    "ambient": {
      "currentDate": "[REDACTED]",
      "currentTime": "[REDACTED]",
      "dayOfWeek": "[REDACTED]",
      "environment": "production",
      "orchestrator": "Forge",
      "timezone": "UTC"
    },
    "executionOutputHistory": ["[model output]"],
    "executionPlan": {
      "is_sequential": false,
      "reasoning": "Direct single-step execution path.",
      "steps": [{
        "capability": "chat",
        "depends_on": null,
        "modality": "text",
        "step_id": 1,
        "task_instruction": "[refined prompt]",
        "tool_calls": null
      }]
    },
    "intentResult": "[intent object]",
    "originalPrompt": "[REDACTED]",
    "principalRoles": ["operator"],
    "refinedPrompt": "[refined prompt object]",
    "tenantId": "[REDACTED]",
    "toolArguments": {},
    "userId": "[REDACTED]"
  }
}
```

`ExecutionState.exportState()` exports `runId`, variables except `attachmentContents`, `inlineAttachments`, `sessionHistory`, and `refinedPrompt`, plus `stepOutputs`; actual variable keys vary with the run (`src/orchestrator/context/state.py`, `ExecutionState.exportState`). Potentially sensitive values still include user/tenant IDs, prompts, attachment routing metadata/names, raw tool arguments, intent and plan instructions, scratchpad, agent messages, model/tool outputs, and the run ID. Inline attachment bytes and extracted attachment content are excluded.

`CheckpointStore._path()` validates tenant, run, and checkpoint components,
resolves them, and checks both root and tenant containment. `save()` uses a
same-directory temporary file, fsync, and atomic replacement; `load()` rejects
expired files. Tenant-path traversal and partial-file writes are covered by
`tests/unit/test_checkpoint_containment.py`.

## 12. Configuration & environment [PARTIAL]

`Settings` uses Pydantic Settings with the `FORGE_` prefix, `.env` loading, and
unknown-variable ignoring. Explicit aliases are used for `HF_TOKEN` and
`OTEL_EXPORTER_OTLP_ENDPOINT`. The checked-in `.env.example` contains optional
deployment identity, mounted paths, secrets, and external endpoints only.

| Variable | Consumer | Required? / purpose |
|---|---|---|
| `FORGE_ENVIRONMENT` | `Settings` / app lifespan | Optional; `development` by default; `production` requires an explicit checkpoint root |
| `FORGE_CHECKPOINT_ROOT` | `CheckpointStore` / readiness route | Optional outside production; defaults to `data/checkpoints`; persistent storage is required in production |
| `FORGE_CHECKPOINT_RETENTION_DAYS` | `CheckpointStore` | Optional; defaults to 30 days; minimum one day |
| `FORGE_AUDIT_LOG_PATH` | `AuditLog` | Optional deployment path override; defaults to `logs/forge-audit.jsonl` |
| `FORGE_SANDBOX_ROOT` | `computer/workspace.py` | Optional deployment mount; defaults to the computer package directory |
| `FORGE_MODEL_CACHE_DIR` | `InferenceGateway` / `HuggingFaceSource` | Optional deployment path override; defaults to `data/models` |
| `FORGE_INFERENCE_DEVICE` | Inference backends | Optional; defaults to `cpu`; use a supported local device value |
| `FORGE_INFERENCE_MAX_CONCURRENCY` | `InferenceGateway` | Optional; defaults to 4 |
| `FORGE_INFERENCE_TIMEOUT_SECONDS` | `InferenceGateway` | Optional; defaults to 120 seconds |
| `FORGE_MEDIA_ALLOWED_HOSTS` | `MediaConverter` | Optional comma-separated allowlist; required for URL-backed media fetches |
| `FORGE_ALLOW_ANONYMOUS` | `src/orchestrator/security/runtime.py` | Optional; defaults to false; affects only standalone identity resolver |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Tracing configuration | Optional deployment-specific HTTP/protobuf collector URL |
| `FORGE_HF_REPO_ID` | `TrajectoryExporter` | Optional destination; requires `HF_TOKEN` with write permission to enable one-way upload |
| `HF_TOKEN` | `HuggingFaceSource` / `HuggingFaceSync` | Optional Hub secret; used for private/gated downloads and, when configured, one-way uploads |

`MAX_ATTACHMENT_BYTES` (10 MiB) and `MAX_MEDIA_BYTES` (20 MiB) are code-owned
limits in `src/orchestrator/settings.py`; they cannot be changed through
environment variables. The trajectory directory defaults to
`logs/trajectories` in code. Repository type for optional Hub upload is fixed
to `dataset`. Sandbox roots, extensions, and temporary retention are defined
in `src/orchestrator/computer/policy.json`.

The settings model also supports JSON mappings for inference backend and
source overrides; those have active gateway consumers but are not listed in
`.env.example`. The settings model does not expose unused artifact-store,
remote-backend, or quantization fields.

## 13. Observability [PARTIAL]

- Application logging/structured request logging is absent; the active run uses the JSONL `AuditLog`.
- Audit redaction covers selected keys and bearer strings, not arbitrary sensitive prompt/file contents. Current event details do not normally include prompt or raw attachment data, but checkpoint state can.
- No metrics exporter, tracing instrumentation, health probes, readiness checks, or request correlation middleware is wired.
- `ExecutionBudget.metrics()` returns steps, iterations, tool calls, estimated tokens, elapsed seconds, terminal status, and termination reason. Static synthesis includes these metrics; stream execution does not pass budget metrics into the final synthesizer.
- Draft `/health` and `/ready` routes do not exist at runtime.
- The optional trajectory exporter writes caller-visible prompt/final-response
  pairs in OpenAI JSONL format. It is inactive unless the
  `/v1/responses` request sets `trajectoryExport=true`, and skips
  failed and interactive runs. It does not curate or clean examples. Optional
  Hugging Face synchronization uploads the complete local daily file when
  both repository ID and token are configured; it is one-way, and upload
  failures do not affect the local file or run.

## 14. Tests [PARTIAL]

Test tree includes `test_eval.py`, `test_forge.py`, `test_idempotency.py`, unit
suites for data/local/text/speech tools, consolidated tool/skill contracts,
audio route and STS pipeline behavior, external-tool resume, sandbox,
synthesis, Action IDs, and the end-to-end smoke test. HTTP audio and
external-tool flows use in-process ASGI tests; model-provider connectivity is
stubbed.

Historical post-Round-4/5 validation:

```text
python -m pytest -q
59 passed in 18.91s

python -m pytest tests\unit\test_action_contract.py tests\unit\test_tool_thoughts.py tests\unit\test_api_surface.py -v
5 passed in 20.26s
```

The focused checks cover Action ID uniqueness/catalog documentation, Thought
ID catalog documentation, Action lifecycle and deprecated legacy Thought
compatibility, event redaction, and absence of the obsolete route.

Current validation from the orchestrator project root after Round 15 and
local text-tool updates:

```text
python -m pytest -q
131 passed in 191.33s

Focused tool, skill, action, media, and attachment tests
34 passed
```

Pytest collection is scoped in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".", "tests"]
```

`tests/conftest.py` reads `src/orchestrator/computer/policy.json`, creates a temporary policy/workspace, and sets `FORGE_SANDBOX_ROOT`; it contains no sibling-tree path insertion. The provenance command, run from the `tests` directory with the project root on `PYTHONPATH`, printed:

```text
C:\TediForge\Forge\backend\orchestrator\tests\test_eval.py
```

Exact command:

```powershell
$env:PYTHONPATH = 'C:\TediForge\Forge\backend\orchestrator'
python -c "import test_eval; print(test_eval.__file__)"
```

The current `tests/conftest.py` is:

```python
import json
from pathlib import Path

import pytest


@pytest.fixture
def sandboxWorkspace(tmp_path, monkeypatch):
    projectRoot = Path(__file__).resolve().parents[1]
    sandboxRoot = tmp_path / "sandbox"
    workspaceRoot = sandboxRoot / "workspace"
    for directoryName in ("uploads", "outputs", "tmp"):
        (workspaceRoot / directoryName).mkdir(parents=True, exist_ok=True)
    policy = json.loads((projectRoot / "src" / "sandbox" / "policy.json").read_text(encoding="utf-8"))
    (sandboxRoot / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setenv("FORGE_SANDBOX_ROOT", str(sandboxRoot))
    return workspaceRoot
```

Round 3 baseline validation (before Rounds 4/5 changes):

```text
python -m pytest -q
63 passed in 40.66s

python -m pytest tests\smoke\test_end_to_end.py -v
tests/smoke/test_end_to_end.py::test_forge_engine_runs_end_to_end PASSED
1 passed in 18.64s
```

`tests/smoke/test_end_to_end.py` injects a stub text provider, constructs the default engine/tool registry, runs `say hi` with user/tenant identity and temporary audit/checkpoint paths, then asserts non-empty content and a `run_` ID. The full run and standalone smoke test both pass. No passing test establishes actual model-provider connectivity, successful HTTP request handling, cancellation behavior, concurrent runs, attachment-byte delivery, complete stream persistence/audit, or checkpoint path containment.

The default `CheckpointStore().root` resolves relative to `src/orchestrator/security/durability.py` to `tests/checkpoints`; tests and the smoke test also use temporary checkpoint roots.

The Rounds 4/5 suite removed approval/policy/ABAC/egress helper tests and the
obsolete route test. It added Action ID catalog checks and Action lifecycle,
legacy-event, and redaction coverage. At that historical point no business
route was mounted; current route tests are listed above. Provider connectivity,
concurrent runs, complete stream audit/persistence, and checkpoint path
containment remain unverified.

## 15. Gap register [PARTIAL]

Each row has a status tag. `[RISK]` denotes impact beyond missing feature wiring; status remains a description of current code. Round 3 evidence names the relevant code path and, for absence claims, the caller/whole-source search that demonstrates the missing wiring.

| ID | Area | Status tag | What code does | What docs/intent say | Impact | Suggested owner/priority | Round 3 evidence |
|---|---|---|---|---|---|---|---|
| G-001 | Default engine construction | [RESOLVED] | Registry contains only local schemas/handlers and does not require construction-time event IDs; handlers own Action descriptors | Engine constructs with all registered local tools | Construction does not load external service credentials or clients | Orchestrator / Resolved | D-001, D-010; `ToolRegistry.register_module`; end-to-end smoke and Action contract tests |
| G-002 | HTTP app | [PARTIAL] | Responses, Chat Completions, Models, Embeddings, and batch audio routes are mounted; `/v1/audio/sts` is a WebSocket; `/v1/orchestrate` remains absent | Core backend calls authenticated API routes | Trusted principal middleware and model/provider configuration remain deployment requirements | Core backend/orchestrator / P0 before exposure | `src/orchestrator/api/__init__.py`; HTTP integration tests |
| G-003 | Startup/lifecycle | [PARTIAL] | Lifespan constructs the engine and shuts down the exporter; provider/media client close-all is not implemented | Runtime dependencies should be created and closed as a unit | Some client resources may outlive application shutdown | Orchestrator / P1 | `src/orchestrator/api/__init__.py`; exporter shutdown test |
| G-004 | Empty route modules | [PARTIAL] | Health remains empty; chat completions, embeddings, and models now have mounted routes | Files imply route surfaces | Health surface remains absent | Orchestrator / P1 | `src/orchestrator/api/health.py`; model route integration tests |
| G-005 | Engine filename | [PARTIAL] | `responses/routes.py` contains engine/helpers; `responses/http.py` contains the HTTP router | Path implies HTTP router | The package splits HTTP binding and engine implementation across files | Orchestrator / P2 | `responses/routes.py`; `responses/http.py` |
| G-006 | OpenAPI snapshot | [PARTIAL] | Generated API includes the HTTP routes; WebSocket is not represented | Snapshot must match runtime contract | Stale generated schema may mislead clients | Orchestrator / P1 | `docs/openapi.json`; `app.openapi()["paths"]` |
| G-007 | Request schema binding | [RESOLVED] | `/v1/responses` binds `OrchestratorRequest` and calls `run`/`resume` | Requests reach the engine | HTTP invocation is wired behind trusted `request.state.principal` | Orchestrator / Resolved | `src/orchestrator/api/v1/responses/http.py`; integration cycle test |
| G-008 | Request option enforcement | [PARTIAL] | `reasoning.effort`, `tools`, resume messages, stream, attachments, and `metadata.trainingExport` are mapped; topology and session IDs are server-owned | Schema options should affect execution | Unsupported options must not be assumed effective | Orchestrator / P1 | HTTP mapping and `ForgeEngine.run` signature |
| G-009 | Attachment content | [RESOLVED] | MIME/signature-checked base64 is extracted and injected into classifier/refiner prompts under per-file/total caps; extraction text is excluded from checkpoint exports | Attachment content is usable without persisting user file bytes | Supported images/text reach prompt context; unsupported files fail explicitly | Orchestrator / Resolved | `src/orchestrator/attachments.py::AttachmentDispatcherRouter.extract_content`; `routes.py::ForgeEngine.run`; `context/state.py::ExecutionState.exportState`; `test_attachment_content.py` |
| G-010 | History | [RESOLVED] | Last ten messages reach classifier/refiner and agent prompts in a bounded context block; history is transient and checkpoint snapshots retain names only | Context-aware follow-up requests | Recent context is available without storing historical attachment bytes | Orchestrator / Resolved | `src/orchestrator/context/session.py::SessionManager.recent` and `prompt_block`; `routes.py::ForgeEngine.run`/`resume`; `test_history_context.py` |
| G-011 | Tool argument provenance | [RESOLVED] | `ToolExecutor` validates parsed argument objects against registered JSON Schema and returns typed `INVALID_ARGUMENTS` failures before dispatch | Registered schemas constrain caller-supplied arguments | Invalid arguments do not reach handlers; audit includes error path but no raw arguments | Orchestrator / Resolved | `src/orchestrator/tools/executor.py::ToolExecutor._validated_call`; `routes.py::ForgeEngine._executeToolCall`; `test_tool_argument_validation.py` |
| G-012 | Tool-call budget | [RESOLVED] | Internal calls invoke `record_tool_call()` before dispatch; duplicate fingerprints stop after three repeats; caller-owned external calls are excluded | Default limit allows at most 20 internal calls | Over-budget internal runs terminate as failed with `tool_call_limit` | Orchestrator / Resolved | `src/orchestrator/context/limits.py::ExecutionBudget.record_tool_call`; `routes.py::_executeToolCall`; `test_tool_call_budget.py` |
| G-013 | Evaluator plateau | [PARTIAL] | Engine calls evaluator without score history | Evaluator supports plateau scores | Score-plateau fallback branch is unreachable | Orchestrator / P2 | `ExecutionEvaluator.evaluate(..., previous_scores=None)` at `routes.py:299`; plateau branch `325-328`; static/stream calls at `674`/`793` pass only objective and outputs |
| G-014 | Streaming | [PARTIAL] | Completed output split by whitespace with delay | Stream contract suggests incremental output | Not provider token streaming | Orchestrator / P1 | `_executeGraphStream` at `routes.py:811-826` chunks completed text and sleeps `0.02s`; dispatcher `stream()` is not called |
| G-015 | Conversation title | [REMOVED] | No title generator, route, tool, request field, or response field exists | Clients own their conversation store and decide whether to request titles | The orchestrator performs no title work; see D-013 | Client / Resolved | D-013; route/OpenAPI and request/response contract tests |
| G-016 | Sources | [PARTIAL] | Static source list remains empty; graph does not append | Response supports citations | Sources remain empty absent custom generator | Orchestrator / P1 | `routes.py:604` initializes `sources=[]`; no append in `_executeGraphStatic`; stream graph emits no source event |
| G-017 | Stream completion records | [PARTIAL] | Stream writes planned checkpoint/audit only | Static path records completed run | Stream outcomes lack completed checkpoint/audit | Orchestrator / P1 | `routes.py:472` planned save/audit; static-only branch at `494-495` writes completed; stream returns at `475-481` |
| G-018 | Approval enforcement | [NOT PROVIDED] | Approval scaffolding was removed by D-003; no approval gate exists | Orchestrator does not claim to approval-gate tool writes | External side effects require an authoritative core-backend policy if approval is required | Core backend / As needed | D-003; `src/orchestrator/security/approvals.py` and approval endpoints are absent |
| G-019 | ABAC | [NOT PROVIDED] | ABAC helper was removed by D-003 | Orchestrator does not claim attribute-based authorization | Principal attributes do not affect tool authorization | Core backend / As needed | D-003; no ABAC module or engine call |
| G-020 | Egress allowlist | [NOT PROVIDED] | General egress helper was removed by D-003; bounded media conversion and public-web search have their own URL checks | Orchestrator does not claim a general outbound-host policy | Deployments must control network egress outside those tool-specific checks | Platform / As needed | D-003; no general egress module |
| G-021 | Production identity | [RISK] | Responses requires a `Principal` in request state; token verification middleware is outside this package | Authenticated tenant identity expected at the core-backend boundary | Misconfigured upstream integration cannot authenticate Responses calls | Core backend / P0 before HTTP exposure | `responses/http.py`; trusted middleware contract; no identity headers accepted |
| G-022 | SDK runner | [LIBRARY ONLY] | OpenAI Agents SDK wrapper not invoked by custom engine | SDK agent path exists in source/docs | Two agent execution architectures can drift | Orchestrator / P2 | `src/ochestrator/runner.py` defines SDK wrapper; `routes.py:364-366` creates custom `AgentRegistry` and no runner call occurs in `run()` |
| G-023 | Checkpoint path and retention | [RESOLVED] | Root/tenant containment, component validation, atomic replacement, and 30-day expiry are enforced | Suspended runs must be safely recoverable | Traversal and unbounded-retention paths are addressed; storage remains plaintext | Orchestrator / Resolved | `src/orchestrator/security/durability.py`; `tests/unit/test_checkpoint_containment.py` |
| G-024 | Default provider wiring | [PARTIAL] | Chat, embeddings, speech, and transcription use lazy local runtimes; image/video generation has no public route | Catalog names imply reachable models | Model weights may be absent and first use may need Hub access | Orchestrator / P1 | `HuggingFaceInference`; `src/orchestrator/api/v1/models/routes.py`; speech dispatcher tests |
| G-025 | Hugging Face model runtime | [RESOLVED] | Hub snapshots are downloaded locally and loaded using the declared runtime; inference is local | Model parameters and runtime selection must affect local execution | No hosted inference request is made; downloads require network only on cache miss | Orchestrator / Resolved | D-018; local model and no-remote-inference tests |
| G-026 | App/client cleanup | [PARTIAL] | Lifespan closes cached local model runtimes, speech runtimes, training worker, and media converter | Long-lived ASGI service expected | Injected app-state providers remain caller-owned | Orchestrator / P1 | `src/orchestrator/api/__init__.py`; model provider lifecycle |
| G-027 | Errors/cancellation | [PARTIAL] | No top-level error/failure audit/finalizer | Status/error schemas exist | Inconsistent propagated errors; cancellations unrecorded | Orchestrator / P1 | `routes.py:373-511` has no enclosing failure/finally lifecycle; emitted run audit events are only planned/completed at `472`/`495` |
| G-028 | Concurrency | [RISK] | Per-run state local; shared clients/audit/checkpoint lack complete synchronization | Service expected to handle concurrent requests | Safety is not established for singleton engine | Orchestrator / P1 | `executor.py:70-74` mutates lazy initialization without a lock; `audit.py:31-44` appends without lock; §7 concurrency table lists unverified cases |
| G-029 | Metrics/tracing | [UNWIRED] | Only return metadata and JSONL audit | Runtime observability expected | No production health, metrics, or distributed trace | Platform/orchestrator / P2 | `api/__init__.py:7-8` mounts no instrumentation; `src/orchestrator/api` has no middleware/exporter; §13 |
| G-030 | Dependency reproducibility | [RISK] | Requirements use ranges; no project-local environment/lock evidence | Container should build reproducibly | Resolution can drift across builds; project-local reproducibility unassessed | Platform/orchestrator / P2 | `requirements.txt` contains ranges; no project-local `.venv` or lockfile is present; global `pip list --outdated` was excluded as non-project evidence |
| G-031 | Package spelling | [DEAD / STALE] | `src/ochestrator/` is misspelled and not used by `ForgeEngine.run` or FastAPI | Package name is intended to mean orchestrator | Confusing imports and duplicated execution architecture | Orchestrator / P2 | `src/ochestrator/runner.py` defines SDK wrapper; search of engine and `src/orchestrator/api` finds no import or invocation |
| G-032 | Engine class rename compatibility | [RESOLVED] | In-repository consumers now use `ForgeEngine`; serialized state/audit fields contain run IDs and data, not Python class symbols | Previous Python consumers may have imported the old symbol | No in-repository compatibility surface or persisted-format migration required | Orchestrator / Resolved | Repository search finds no old-symbol references; `state.py:50-56` and `audit.py:31-40` serialize data fields only; no external-consumer evidence was found |
| G-033 | Event ID catalog sync | [RESOLVED] | Tests verify registered Action IDs are valid, unique, and documented, and emitted Thought ID literals are documented | Handler-owned IDs and catalogs must stay synchronized | Catalog drift is caught in the test suite | Orchestrator / Resolved | `tests/unit/test_action_contract.py` |
| G-034 | Chat Completions training boundary | [RESOLVED] | Forge Text Chat Completions contains no exporter call; integration test asserts no export line | Only opted-in completed Responses runs may be collected | Regression is caught by HTTP test | Orchestrator / Resolved | `tests/integration/test_training_export_toggle.py`; source search of `src/orchestrator/api/v1/chat` |
| G-035 | Checkpoint deployment protection | [RISK] | Checkpoint files are plaintext and restart recovery requires a persistent mounted root | Deployment must protect sensitive execution state at rest | Ephemeral/unprotected storage can lose or expose suspended runs | Platform/orchestrator / P0 before production | D-004; `FORGE_CHECKPOINT_ROOT`; §11 |
| G-036 | Uniform tool operation contract | [RESOLVED] | Every default registry schema requires an operation enum and every registered operation has an implementation | D-020/D-021 require an operation field, implemented skill row, and Action ID per registered operation | Schema/skill/catalog drift or placeholders fail unit tests | Orchestrator / Resolved | `test_tool_operations_audit.py`; `test_action_contract.py`; D-020; D-021 |
| G-037 | Stateful tool ownership | [RESOLVED] | Built-in todo/memory storage and `state_store.py` were removed | Durable tool state belongs to callers or the core backend | Local tools cannot retain task or memory state across requests | Orchestrator / Resolved | D-022; `test_no_stateful_tools.py`; `test_no_persistence_in_tools.py` |

## 16. Recommended next steps [PLANNED]

1. Implement provider factory and deployment settings, then close provider and media clients through explicit lifespan ownership.
2. Keep the current no-business-route boundary. If the core backend later requires HTTP access, define the internal contract and authenticated caller boundary before adding an endpoint; do not treat `responses` as an HTTP router.
3. Move checkpoints out of `tests/`, define encryption/retention, and audit static and streamed success/failure/cancellation consistently.
4. Establish real provider streaming; add source provenance and stream/concurrency/cancellation integration tests.
5. Establish project-local dependency locking and deployment health/metrics after the runtime contract and service lifecycle are defined.

## Round 3 verification log [HISTORICAL]

| Check | Result | Evidence |
|---|---|---|
| C-1 — Generated OpenAPI paths | Historical | Round 3 dump included `POST /v1/orchestrate`; current draft/runtime paths are empty |
| C-2 — Default engine / Canva Thought IDs | Resolved | D-001 removes registry-level IDs; default engine constructs without Thought-ID metadata |
| C-3 — Stream title key mismatch | Confirmed | Collector reads `chunk` at `routes.py:552`; graph emits `content` at `routes.py:824` |
| C-4 — Static source collection | Confirmed | Static graph initializes `sources` at `routes.py:604` and never appends; only the stream wrapper has a source append, and graph emits none |
| C-5 — Tool-call budget | Confirmed | `record_tool_call` is defined at `src/orchestrator/context/limits.py:59`; no engine call site |
| C-6 — Stream terminal persistence/audit | Confirmed | Planned save at `routes.py:471`; only static branch saves `completed`/records `run.completed` at `routes.py:494-495` |
| C-7 — Empty route modules | Confirmed | Chat completions, embeddings and models route files measured at 0 bytes; no route definitions |
| C-8 — Engine option signature | Confirmed | `ForgeEngine.run` signature at `routes.py:373` omits mode, forcedModality, idempotencyKey and metadata |
| C-9 — History field bound | Confirmed | `HistoryMessage.content` at `src/orchestrator/schemas/input.py:55` declares `max_length=8000` |
| C-10 — Test result | Historical baseline | Round 3 `63 passed`; post-Round-4/5 results are recorded below |
| C-11 — Pytest isolation | Confirmed | `pyproject.toml` pins `testpaths = ["tests"]`; `conftest.py` content and direct import path are reproduced in §14 |
| C-12 — Route contract | Removed | The 501 route and `tests/unit/test_orchestrate_route.py` were deleted by explicit decision |
| Added — End-to-end smoke | Passed | Stub provider; `ForgeEngine.run(prompt="say hi", ...)` returns non-empty content and `run_` ID |
| Added — Audit record | Captured/redacted | A generated `run.planned` JSONL line is reproduced in §11 with IDs/time redacted |
| Added — Provider/lifespan blueprint | Proposed only | §6 explicitly lists missing settings object, provider factory, and registry close-all API |
| Added — G-011 remediation | Proposed only | §9 retains schema-validation options; policy/approval insertion was removed by D-003 |
| Added — Dependency evidence | Partial | No project-local environment/lock; global outdated-package data excluded and no vulnerability claim made |

## Round 4/5 verification log [IMPLEMENTED]

| Check | Result | Evidence |
|---|---|---|
| Old route removal | Confirmed | `/v1/orchestrate` stub and route test deleted; no route moved to `responses` |
| Thought/Action IDs | Confirmed | Registry no longer stores IDs; `test_action_contract.py` checks shape, uniqueness, and documentation |
| Thought/Action/Status contract | Confirmed | Stream schema admits five event types; action lifecycle and run status are synthesized separately |
| Policy scope | Confirmed | D-003; approval, policy, ABAC, egress code/tests removed; RBAC on `orchestrate:run`, audit, durability and Principal retained |
| Full test suite | Passed | `python -m pytest -q`: `59 passed in 18.91s` |
| Focused event and API checks | Passed | Action/Thought catalog, lifecycle, redaction, and obsolete-route tests: `5 passed in 20.26s` |

## Open questions for reviewers [PLANNED]

- Should the orchestrator's HTTP API be mounted here, or should the core backend be the only public HTTP service and call an internal orchestrator interface?
- Which identity token/claims contract is authoritative, and where must signature, issuer, audience, and tenant membership be verified?
- What should the production checkpoint backend, encryption, retention, and recovery guarantees be?
- Which attachment types must be supported, and where should bytes be stored/decoded so they do not enter checkpoints or logs accidentally?
- Should `mode`, `forcedModality`, metadata, history and idempotency be implemented, or removed from the public contract until supported?
- Is the OpenAI Agents SDK runner a supported second execution path or should its wrapper/helpers be retired?
- What concurrency guarantees are required for shared media clients and audit writes?
- Should the legacy top-level `Forge/ochestrator` tree be removed, archived, or retained as a distinct compatibility project? It is no longer involved in this project's pytest collection.
- Should `src/ochestrator/` be renamed or removed, given the typo and parallel SDK wrapper?
