# D-013: Title Generation Is Client-Owned

- **Status:** Accepted
- **Date:** 2026-11-11
- **Owner:** Orchestrator
- **Related:** [D-006: CamelCase wire contract and central tool validation](./D-006-wire-camelcase-and-validation.md)

## Context

The orchestrator is stateless and does not own conversation records. A client
knows whether it stores conversations, when a title is needed, and whether
title generation is enabled.

## Decision

Conversation title generation belongs to the client. The orchestrator does
not generate titles automatically and does not expose a title endpoint, tool,
request field, or response field.

## Consequences

- Clients may generate and store titles using their own model workflow.
- Headless and non-conversational clients do not incur title-generation work.
- Orchestrator API and runtime documentation must not imply that title
generation is implemented here.
