# D-010: The Orchestrator Owns No Service Integrations

- **Status:** Accepted
- **Date:** 2026-11-10
- **Owner:** Orchestrator
- **Related:** [D-004: External tools use two-phase resume](./D-004-external-tools-two-phase-resume.md), [External tools reference](../references/external-tools.md), [Orchestrator Runtime](../architecture/orchestrator-runtime.md)

## Context

Service-specific adapters and skills make the orchestrator a credential host
and an integration maintainer. The orchestrator's responsibility is executing
local tools and coordinating runs, not owning GitHub, Gmail, Google Calendar,
Slack, Notion, Linear, Canva, Hevy, or Tripsy access.

## Decision

The orchestrator owns no external service integrations. External services are
caller-owned `tools`, suspended with `call_id` and resumed through a
`function_call_output` item in `messages` under D-004. The caller owns credentials, adapters,
policy, and any service-specific skills. `src/tools/definitions/` contains
only local tools; `src/skills/tools/` contains skills only for those tools.

## Consequences

- No service credential is held by the orchestrator.
- Service API changes do not require changes to the orchestrator.
- Callers must supply their own external function schemas and execute returned
  function calls.
- The caller may ship its own skill; external service skills do not live in
  the orchestrator's `src/skills/`.
- The existing external-tool suspension/resume path remains the interface;
  this decision does not change it.

## Alternatives considered

- Keep adapters but make credentials optional — rejected because the code
  remains an integration surface and still needs maintenance.
- Move adapters to a separate orchestrator package — rejected because it
  preserves the same ownership boundary.
- Gate adapters behind an environment flag — rejected because disabled code
  is still shipped and maintained.
- Keep only selected services — rejected because integration policy belongs
  to the caller.

**Boundary:** the orchestrator owns local execution; the caller owns external
services. `tools` is the interface between them.
