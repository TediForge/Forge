# Forge Orchestrator

Forge Orchestrator is a Python service for coordinating text, document, image,
video, data, and audio tasks through one API. It combines request validation,
planning, specialist agents, local tools, model dispatch, and response
synthesis. Inference is routed through a registry and gateway that separate
model capabilities, artifact sources, and execution backends.

> **Runtime note:** The FastAPI lifespan owns a shared, lazy-loading inference
> gateway. The default local source is Hugging Face Hub; explicit local paths
> are supported without network access. Upstream trusted-principal middleware
> is still required before exposing protected routes.

## Table of contents

- [Features](#features)
- [System architecture](#system-architecture)
- [Workflow examples](#workflow-examples)
- [Technology stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Run the service](#run-the-service)
- [Building the Computer Image](#building-the-computer-image)
- [Python usage](#python-usage)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

## Features

- FastAPI endpoints for orchestration, chat, model discovery, embeddings, and
  audio.
- Local model inference through Transformers, Diffusers,
  Sentence-Transformers, faster-whisper, and Piper.
- Registered local tools for document, data, image, video, and other supported
  operations.
- A computer tool that runs bounded commands and manages workspace files in
  disposable Firecracker microVMs on Linux/KVM deployments.
- Declarative Ubuntu guest image manifests and a Linux rootfs builder for
  pre-installed Python, Node.js, PHP, and Go runtimes.
- Structured Thought, Action, and Status events, including streaming responses.
- Provider-backed token streaming for the local Transformers text runtime.
- Caller-owned external tools that can suspend a run and resume with the
  caller's result.
- Input validation, execution limits, terminal audit records, and durable
  checkpoints.
- `/health`, `/ready`, Prometheus-format `/metrics`, request IDs, and
  OpenTelemetry spans when an exporter is configured.

## System architecture

The service is a Python orchestration implementation built on FastAPI,
Pydantic, and Forge's own engine, agents, and tool registry. It does not use
LangChain or LlamaIndex. Its public request and response shapes are API
contracts, not a requirement to use any particular hosted model provider.

```text
Trusted caller / core backend
          │
          ▼
FastAPI routes ──► Pydantic validation and access checks
   │                         │
   ├─ Responses              └─ Base64 media and attachment limits
   ├─ Chat / models / embeddings
   └─ Transcription / speech / real-time audio
          │
          ▼
Forge orchestration engine
  classify ──► refine ──► plan ──► select agent / invoke local tool
                                         │
                  ┌──────────────────────┼───────────────────────┐
                  ▼                      ▼                       ▼
          Inference Gateway      Local tool registry       Caller-owned tools
             ▲       ▲           PDF, data, image,          suspend the run;
             │       │           video, search, etc.         caller executes
       Sources     Backends                                   and resumes it
       Hub/local   Transformers, Piper,
                   Whisper, Diffusers
                  └──────────────────────┼───────────────────────┘
                                         ▼
                          Synthesize response and events
                          Save configured checkpoints/audit

```

On Linux/KVM deployments, the `computer` tool routes command and workspace
operations to disposable Firecracker guests. It does not execute commands in
the Orchestrator process. Its warm pool scales on demand to a code-owned limit
of 200 instances, further capped by detected host/cgroup memory; same-run
operations are serialized and queued acquisition times out after 30 seconds.
Snapshot-based cloning is not enabled because restoring one snapshot
concurrently can duplicate guest identity and randomness. See the
[computer runtime guide](docs/guides/computer-runtime.md) for guest image and
service requirements.

The registry binds model IDs and capabilities to a source and default backend.
The gateway resolves artifacts and owns backend caching, execution limits,
metrics, and shutdown. Hugging Face is one source; local filesystem paths do
not require network access. Transformers is the required local backend;
vLLM, SGLang, TensorRT-LLM, llama.cpp, and remote OpenAI-compatible backends
are optional and are not yet production implementations. Public Hub repositories
do not require a token; `HF_TOKEN` is only needed for private or gated
repositories.

The application creates one `InferenceGateway` per lifespan and closes it
after serving. Engine and tools use that gateway or modality facades; model
backends and Hub clients remain inside `orchestrator.inference`. The local
Transformers backend emits provider token chunks for streaming responses.
Trajectory export is opt-in.

## Workflow examples

These are examples of how callers can combine the service's current
capabilities. They are not hard-coded business workflows; model-backed
orchestration examples require the relevant provider to be configured.

### 1. Document intake and summary

```text
PDF / supported document
  └─► validate a base64 attachment and extract supported text
       └─► make the text available to local extract / summarize operations
            └─► synthesize a response
```

The caller submits attachment bytes as base64 with a declared MIME type.
Pydantic validates the encoded input and size limits. The registered PDF,
extract, and summarize tools support their documented operations. The PDF
tool reads a path inside its sandbox; the calling application must stage an
uploaded file into an authorized workspace before asking that tool to read it.
Any model-backed classification, planning, or reasoning step requires an
injected text provider; the default orchestration engine does not supply one.

### 2. Spreadsheet analysis

```text
CSV / spreadsheet in an authorized workspace + question
  └─► validate request and file limits
       └─► local spreadsheet / data operations
            └─► structured result, chart, or report
```

Use the registered spreadsheet and data tools for their implemented
operations. Keep data authorization and any external storage or delivery in
the calling application. This service does not silently send uploaded files to
a hosted model.

### 3. Local speech conversation

```text
Microphone audio
  └─► local faster-whisper transcription
       └─► Forge orchestration / response
            └─► local Piper speech synthesis
                 └─► audio response
```

The batch transcription and speech endpoints use local runtimes. The
`/v1/audio/sts` WebSocket supports a push-to-talk session using the same local
speech components. Orchestration-backed replies still require a configured
text provider.

### 4. Caller-owned external action

```text
Caller sends tool definitions
  └─► orchestrator returns a function call and suspends
       └─► caller authorizes and executes the action
            └─► caller submits the result with the response ID
                 └─► orchestrator resumes and returns the final response
```

The caller remains responsible for authorization, credentials, and execution
of external services. See [the external-tools contract](docs/references/external-tools.md).
To resume, send the matching function output to the same Responses endpoint:

```http
POST /v1/responses
Content-Type: application/json

{
  "previous_response_id": "run_abc123",
  "messages": [
    {
      "type": "function_call_output",
      "call_id": "call_123456",
      "output": "{\"number\":42}"
    }
  ]
}
```

There is no separate `/resume` route.

Successful Responses include a `sources` array. Each source uses the
`SourceReference` contract; document-specific details such as file and page
are carried in `metadata`:

```json
{
  "runId": "run_abc123",
  "status": "completed",
  "content": [{"type": "text", "text": "The report shows steady growth."}],
  "sources": [
    {
      "title": "report.pdf, page 4",
      "url": "report.pdf#page=4",
      "sourceType": "document",
      "metadata": {"file": "report.pdf", "page": 4}
    }
  ]
}
```

## Technology stack

- Python 3.11+
- FastAPI, Pydantic, and Uvicorn
- PyTorch, Transformers, Diffusers, and Sentence-Transformers
- faster-whisper and Piper for local audio
- Hugging Face Hub for model-weight downloads
- Pytest for automated tests

## Prerequisites

- Python 3.11 or newer.
- Network access on first use to download public model weights.
- Linux with `/dev/kvm`, Firecracker, and a prepared guest image only if the
  `computer` tool is enabled; see the [computer runtime guide](docs/guides/computer-runtime.md).
- Sufficient disk space and memory for the selected local models. Diffusion
  and video models may require substantial resources.
- FFmpeg and Tesseract for the corresponding media and OCR tools when running
  outside the supplied Docker image. The Dockerfile installs both.

## Installation

Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

On macOS or Linux, activate the environment with
`source .venv/bin/activate` instead.

## Configuration

Copy [.env.example](.env.example) to `.env`. It lists deployment identity,
persistent storage, model device, secrets, and optional deployment endpoints;
code-owned defaults and safety limits are not environment variables.

Treat Hub tokens as secrets. Trajectory export requires explicit
`trajectoryExport=true` on a completed autonomous Responses request; it writes
bounded, redacted JSONL to `logs/trajectories` by default. Hub upload is
optional and is configured with `FORGE_HF_REPO_ID` and `HF_TOKEN`; the token
must have permission to write to the destination repository. See
[the trajectory export decision](docs/decisions/D-005-training-export-scope.md).

No cloud inference API key is required by the current project configuration.
The local model catalog downloads model weights from the Hugging Face Hub.
`HF_TOKEN` is the optional Hub credential for private/gated downloads and,
when configured, optional export uploads; it is not a hosted inference key.
Set `FORGE_ENVIRONMENT=production` and an explicit
`FORGE_CHECKPOINT_ROOT` for deployments; startup fails if the production
checkpoint root is not configured. Checkpoint and audit storage should be on
durable, access-controlled storage.

## Run the service

Start the development server from the repository root:

```powershell
uvicorn orchestrator.api:app --host 127.0.0.1 --port 8000 --reload --env-file .env
```

Open the interactive API documentation at
[`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs). The model catalog
can be queried with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/models
```

`GET /health` reports process liveness, `GET /ready` checks checkpoint
writability and required local text weights, and `GET /metrics` exposes
in-process run counts, aggregate duration, tool calls, and estimated tokens.
Configure `OTEL_EXPORTER_OTLP_ENDPOINT` to export the instrumented classify,
refine, plan, agent/model, tool, and stream-synthesis spans.

`/v1/responses`, chat, embeddings, and audio operations require a trusted
middleware layer to populate `request.state.principal`. The current FastAPI
application does not implement that authentication boundary itself; do not
expose it directly to untrusted clients.

## Python usage

The inference gateway can also be called directly. This example resolves the
registered local text model through the configured source and backend.

```python
import asyncio

from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest


async def main() -> None:
    gateway = InferenceGateway()
    try:
        response = await gateway.infer(InferenceRequest(
            model_id="text",
            modality="text",
            input="Summarize why local inference can reduce data exposure.",
        ))
        print(response.output)
    finally:
        await gateway.close()


asyncio.run(main())
```

This project uses its own FastAPI routes, model registry, and orchestration
engine rather than LangChain or LlamaIndex. To call the full Responses engine
directly, provide an authenticated `Principal` and inject any required
dispatchers; consult the
[runtime architecture](docs/architecture/orchestrator-runtime.md) and
[wire contract](docs/references/wire-contract.md).

## Building the Computer Image

The computer runtime includes declarative image manifests in
[`src/orchestrator/computer/images/manifests/`](src/orchestrator/computer/images/manifests/).
On a Linux host with Docker, `mkfs.ext4`, loop mounts, and root privileges,
build the default 4 GiB sparse root filesystem with:

```bash
sudo env PYTHONPATH=src python -m orchestrator.computer.images.builder \
  --manifest base \
  --output /var/lib/firecracker/rootfs.ext4
```

For a smaller Python-only runtime, use `--manifest python-only`. The image
builder installs systemd, the non-root guest agent, and the runtimes listed in
the selected manifest. The root filesystem is mounted read-only by
Firecracker; `/workspace`, `/tmp`, and runtime state are temporary. Package
downloads happen while building the image; the guest has no network interface.
See the [computer runtime guide](docs/guides/computer-runtime.md) for kernel,
KVM, and service configuration details.

## Project structure

```text
.
├── src/
│   └── orchestrator/
│       ├── agents/             Specialist agents
│       ├── api/                FastAPI routes and lifespan
│       ├── context/            Run state, limits, and metrics
│       ├── engine/engine.py    ForgeEngine and graph execution
│       ├── export/             Opt-in trajectory export
│       ├── inference/          Registry, gateway, sources, backends, facades
│       ├── computer/           Firecracker guests and filesystem policies
│       ├── security/           Identity, RBAC, audit, checkpoints
│       ├── synthesis/          Response formatting and SSE
│       └── tools/              Local tools and tool execution
├── docs/
│   ├── architecture/           Runtime architecture
│   ├── decisions/              Architecture decision records
│   └── references/             API and tool contracts
├── tests/                      Unit, integration, and smoke tests
├── .env.example                Environment template
├── CONTRIBUTING.md             Contribution process
├── LICENSE                     Proprietary license
├── pyproject.toml               Package and dependency metadata
├── requirements.txt             Container dependency ranges
└── uv.lock                      Resolved dependency lockfile
```

## Testing

Run the test suite from the repository root:

```powershell
python -m pip install pytest
python -m pytest
```

Pytest is configured to collect tests only from `tests/`.
For OpenAPI schema updates and local inference benchmarks, see the
[development guide](docs/guides/development.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a change. Contributions
should include focused tests and update documentation when behavior or public
contracts change.

## License

This repository is proprietary and all rights are reserved. No permission to
use, copy, modify, or distribute the source is granted except by separate
written authorization. See [LICENSE](LICENSE).

## Support

For project questions or defects, open an issue in the
[TediForge Forge repository](https://github.com/TediForge/Forge/issues).
Do not include credentials, private user data, or sensitive production logs.
