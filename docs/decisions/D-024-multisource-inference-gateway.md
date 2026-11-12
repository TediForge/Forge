# D-024: Inference Is Multi-Backend and Multi-Source

- **Status:** Accepted
- **Date:** 2026-11-12
- **Owner:** Orchestrator
- **Related:** [D-018](./D-018-forge-runs-models-locally.md), [Orchestrator Runtime](../architecture/orchestrator-runtime.md)

## Context

Inference is a serving product surface, not a Hugging Face model wrapper.
Model identity and capabilities, artifact acquisition, runtime execution, and
the API used by serving code have different responsibilities. A future
offline post-training package must not enter the serving dependency graph.

## Decision

`orchestrator.inference` owns the model registry, source and backend
contracts, runtime cache, modality facades, and `InferenceGateway`.
Serving-facing code resolves artifacts through sources and runs them through
backends. Hugging Face is one source; explicit filesystem paths and a reserved
artifact-store source are also represented. The Transformers implementation
is the required local default; other backends are optional and must fail with
a clear resolution error if configured but unavailable.

The app lifespan owns the inference gateway and closes it on shutdown.
`orchestrator.rl` is an offline-only scaffold whose future policy artifacts
may be loaded through an inference source. No serving path imports `rl`.

## Consequences

- Model runtime selection may vary by modality or model without changing API
  callers.
- Source and backend behavior can be tested independently with fakes.
- Serving code uses `InferenceGateway` or modality facades; the deprecated
  `orchestrator.models` package is removed rather than kept as a compatibility
  layer.
- Optional backend modules are scaffolds until a working adapter and contract
  tests are provided; they are not advertised as production-ready.
