# D-021: No Registered Placeholder Operations

> **Partially superseded by [D-026](./D-026-agent-computer-layer.md):**
> command execution is now registered only through the isolated Firecracker
> computer runtime; host-process shell execution remains prohibited.

- **Status:** Accepted
- **Date:** 2026-11-11
- **Owner:** Orchestrator
- **Supersedes:** The placeholder exception in [D-020](./D-020-uniform-operation-field.md)
- **Related:** [D-019](./D-019-one-tool-per-domain-one-skill.md), [D-018](./D-018-models-run-locally.md), [Orchestrator Runtime §9](../architecture/orchestrator-runtime.md)

## Context

A registered operation appears in the model-visible schema, its tool skill,
and the Action ID catalog. Returning `NOT_IMPLEMENTED` from such an operation
is a broken contract. Known capabilities must be implemented or removed from
all three surfaces.

## Decision

**No registered operation returns `NOT_IMPLEMENTED`.** An operation that
cannot be implemented with an available and safe backend is removed from its
schema, skill table, and Action ID catalog. `NOT_IMPLEMENTED` may remain as a
future error-code constant, but it is not a result of any registered handler.

Operations backed by optional providers remain implemented and return a
specific configuration or provider error when that deployment dependency is
unavailable. The handler must not fabricate a successful result.

Unrestricted Python/Node/shell execution on the Orchestrator host and
interactive browser click/fill operations are not registered. D-026 defines
the only command-execution exception: commands run inside a disposable,
network-isolated Firecracker microVM. Read-only browser automation is omitted
until an approved browser runtime and navigation policy exist. Image content
analysis/detection, video generation, and PDF table/image extraction are
omitted until their providers are available.

## Consequences

- Every registered operation has executable behavior and a skill row marked
  `implemented`.
- Provider-backed operations report provider/configuration errors explicitly.
- Unsupported capabilities do not consume model-visible schemas or skills.
- The Action ID catalog lists only operations in the active registry.

## Enforcement

- `test_every_operation_is_implemented` exercises all operation enum values.
- `test_no_placeholder_operations_in_skills` checks all skills.
- `test_no_not_implemented_in_handlers` checks registered handler sources.
- Tool/schema/skill/Action ID parity tests remain required.
