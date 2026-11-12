# Forge Orchestrator

Forge Orchestrator is a Python service for coordinating text, document, image,
video, data, and audio tasks through one API. It combines request validation,
planning, specialist agents, local tools, model dispatch, and response
synthesis. Model inference runs locally; public model weights are downloaded
from the Hugging Face Hub when first needed.

> **Runtime note:** The HTTP application is mounted, but not every capability
> is ready by default. In particular, the `ForgeEngine` text and image
> dispatchers need an injected provider for model-backed orchestration. The
> dedicated model routes load their registered local models; transcription and
> speech synthesis use local faster-whisper and Piper runtimes.

## Table of contents

- [Features](#features)
- [System architecture](#system-architecture)
- [Workflow examples](#workflow-examples)
- [Technology stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Run the service](#run-the-service)
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
- Structured Thought, Action, and Status events, including streaming responses.
- Caller-owned external tools that can suspend a run and resume with the
  caller's result.
- Input validation, execution limits, audit records, and durable checkpoints.

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
                  ┌──────────────────────┼──────────────────────┐
                  ▼                      ▼                      ▼
           Local model runtimes    Local tool registry     Caller-owned tools
           Transformers,           PDF, data, image,       suspend the run;
           Diffusers, embeddings,  video, search, etc.     caller executes
           faster-whisper, Piper                          and resumes it
                  └──────────────────────┼──────────────────────┘
                                         ▼
                          Synthesize response and events
                          Save configured checkpoints/audit
```

Local model weights are fetched from the Hugging Face Hub and run on the
application machine. Public repositories do not require a Hub token; `HF_TOKEN`
is only needed for private or gated repositories. No hosted-model API key is
required by this project configuration. Web search and model-weight downloads
do require network access.

The default `ForgeEngine()` does not configure text or image providers.
Applications that use model-backed `/v1/responses` orchestration must inject
the intended providers. The dedicated chat, embeddings, model-catalog, and
audio routes have their own local model paths.

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
Copy-Item .env.example .env
python -m pip install pytest
```

On macOS or Linux, activate the environment with
`source .venv/bin/activate` instead.

## Configuration

Copy `.env.example` to `.env` and adjust only the settings needed for your
deployment:

```env
# Persistent checkpoint directory
FORGE_CHECKPOINT_ROOT=data/checkpoints

# Request size limits
FORGE_MEDIA_MAX_BYTES=20971520
# FORGE_MEDIA_ALLOWED_HOSTS=cdn.example.com,assets.example.org
FORGE_ATTACHMENT_MAX_BYTES=10485760

# Optional Hugging Face Hub token for private or gated model weights
HF_TOKEN=

# Training export is disabled unless enabled here and requested per Responses call
FORGE_TRAINING_EXPORT_ENABLED=false
FORGE_TRAINING_EXPORT_DIR=logs/training-export

# Optional one-way upload of exported JSONL files
FORGE_HF_SYNC_ENABLED=false
FORGE_HF_TOKEN=
FORGE_HF_REPO_ID=
FORGE_HF_REPO_TYPE=dataset
```

Treat Hub tokens as secrets. Training export and Hub synchronization are
disabled by default. Do not enable them unless the data-handling requirements
for the deployment explicitly allow it. See
[the training export decision](docs/decisions/D-005-training-export-scope.md).

No cloud inference API key is required by the current project configuration.
The local model catalog downloads model weights from the Hugging Face Hub;
optional Hub tokens are for gated/private downloads or the separately disabled
upload feature, not hosted inference.

## Run the service

Start the development server from the repository root:

```powershell
uvicorn src.api:app --host 127.0.0.1 --port 8000 --reload --env-file .env
```

Open the interactive API documentation at
[`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs). The model catalog
can be queried with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/models
```

`/v1/responses`, chat, embeddings, and audio operations require a trusted
middleware layer to populate `request.state.principal`. The current FastAPI
application does not implement that authentication boundary itself; do not
expose it directly to untrusted clients.

## Python usage

The local model implementation can also be called directly. This example uses
the registered local text model through Transformers; the model is downloaded
on first use and then loaded for local inference.

```python
import asyncio

from src.core.models.huggingface import HuggingFaceInference


async def main() -> None:
    model = HuggingFaceInference(model="text")
    try:
        answer = await model.generateText(
            "Summarize why local inference can reduce data exposure."
        )
        print(answer)
    finally:
        await model.close()


asyncio.run(main())
```

This project uses its own FastAPI routes, model registry, and orchestration
engine rather than LangChain or LlamaIndex. To call the full Responses engine
directly, provide an authenticated `Principal` and inject any required
dispatchers; consult the
[runtime architecture](docs/architecture/orchestrator-runtime.md) and
[wire contract](docs/references/wire-contract.md).

## Project structure

```text
.
├── src/
│   ├── agents/                 Specialist agents
│   ├── api/                    FastAPI routes
│   ├── context/                Run state, limits, and checkpoints
│   ├── core/models/            Local model registry and dispatchers
│   ├── export/                 Opt-in training export
│   ├── sandbox/                File and execution boundaries
│   ├── synthesis/              Response formatting
│   └── tools/                  Local tools and tool execution
├── docs/
│   ├── architecture/           Runtime architecture
│   ├── decisions/              Architecture decision records
│   └── references/             API and tool contracts
├── tests/                      Unit, integration, and smoke tests
├── .env.example                Environment template
├── CONTRIBUTING.md             Contribution process
├── LICENSE                     Proprietary license
└── requirements.txt            Runtime dependencies
```

## Testing

Run the test suite from the repository root:

```powershell
python -m pip install pytest
python -m pytest
```

Pytest is configured to collect tests only from `tests/`.

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
[TediForge Ochestrator repository](https://github.com/TediForge/ochestrator/issues).
Do not include credentials, private user data, or sensitive production logs.
