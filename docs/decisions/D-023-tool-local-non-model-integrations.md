# D-023: Keep Non-Model Integrations in Their Tool Modules

- **Status:** Accepted
- **Date:** 2026-11-10
- **Owner:** Orchestrator
- **Related:** [D-010](./D-010-orchestrator-owns-no-service-integrations.md), [Provider and Tool Boundary](../references/provider-vs-tool.md), [Orchestrator Runtime](../architecture/orchestrator-runtime.md)

## Context

`src/core/models/adapters/` contains AI model dispatchers and model-runtime
integrations. The Open-Meteo client is ordinary HTTP code for the weather
tool, not a model adapter. Keeping it in the model package misstates its
purpose and separates a tool's implementation across unrelated directories.

## Decision

**Keep the `src/core/models/adapters/` package for AI model integrations.**
Non-model code used only by one tool belongs in that tool's definition
module. The Open-Meteo client and its provider error are implemented in
`src/tools/definitions/weather.py`; tool execution does not require a
weather-specific adapter injection from the engine.

Shared, cross-tool infrastructure may remain in an appropriate shared
package when it is genuinely reused; it must not be put under the model
package merely because it has an adapter-like interface.

## Consequences

- The weather tool owns its request construction, HTTP call, and provider
  error mapping.
- `ForgeEngine` no longer constructs or injects an Open-Meteo adapter.
- AI dispatchers remain separate from ordinary tool-specific service calls.

## Enforcement

- No `weather.py` provider module exists under
  `src/core/models/adapters/`.
- The weather implementation and its HTTP client live together in
  `src/tools/definitions/weather.py`.
