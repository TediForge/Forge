# D-003: Remove Unwired Approval and Policy Scaffolding

- **Status:** Accepted
- **Date:** 2026-11-09
- **Owner:** Orchestrator
- **Related:** [Orchestrator Runtime](../architecture/orchestrator-runtime.md), [D-002](./D-002-separate-thoughts-from-actions.md)

## Context

Approval storage, tool policy evaluation, ABAC helpers, and egress allowlists
were present as standalone code and tests but were not wired into the engine's
tool execution path. Their presence suggested enforcement that did not occur.

## Decision

Remove `ApprovalStore`, `PolicyEngine`, ABAC, and egress-policy scaffolding and
their isolated tests. Retain RBAC authorization on `orchestrate:run`,
`Principal`, audit logging/redaction, checkpoint durability, and the identity
resolver. The identity resolver is owned by the core backend's authenticated
caller boundary; it is not an orchestrator tool-policy mechanism.

Removing these helpers does not claim that external side effects are approval
gated or outbound destinations are allowlisted. Any future policy/approval
control must be designed and enforced at the authoritative core-backend
boundary or introduced as a new decision with end-to-end integration tests.

## Consequences

- Removed code no longer implies controls that the execution path did not
  enforce.
- RBAC, audit, durability, and principal identity remain unchanged.
- Approval and outbound-egress enforcement are explicitly not provided by
  this orchestrator implementation.

## Alternatives considered

- Keep dormant helpers and document them as planned: rejected because their
  APIs/tests imply protection without actual enforcement.
- Wire approval and egress policy into the orchestrator now: rejected as
  outside the requested scope and the core backend's ownership boundary.
