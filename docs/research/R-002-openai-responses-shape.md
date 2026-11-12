# R-002: OpenAI Responses API Shape

- **Date checked:** 2026-11-11
- **Purpose:** Record the reference contract for the orchestrator's compatible Responses surface.

## Findings

OpenAI documents Responses as a request/response API for model generation and
tool use. It is a wire-contract reference, not a provider dependency for
Forge's local orchestration pipeline.

## Sources

- [OpenAI Responses API guide](https://developers.openai.com/api/docs/guides/text)
- [OpenAI API reference](https://developers.openai.com/api/reference)

## Application

The source pages describe OpenAI's product. Forge's supported request fields
and execution behavior remain defined by its own schema, wire-contract
reference, and tests.
