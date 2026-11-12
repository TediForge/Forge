# D-022: No Stateful Tools

- **Status:** Accepted
- **Date:** 2026-11-10
- **Owner:** Orchestrator
- **Related:** [D-004](./D-004-external-tools-two-phase-resume.md), [D-010](./D-010-orchestrator-owns-no-service-integrations.md), [Orchestrator Runtime](../architecture/orchestrator-runtime.md)

## Context

The built-in `todo` and `memory` tools wrote cross-request state to
`src/tools/state_store.py`, a local SQLite database. This made a tool
responsible for persistence, retention, tenant isolation, and database
lifecycle that belong to the caller or core backend, not the orchestrator.
An in-process cache is not an adequate replacement: tasks and memories are
expected to survive process restarts, while a cache would silently lose them.

The orchestrator also has run checkpoints and audit records for its
orchestration lifecycle. Those are not tool-owned state and remain governed
by their existing runtime contracts, including D-004. This decision removes
tool-managed persistent state; it does not change run checkpoint or audit
behavior.

## Decision

**No built-in tool may persist state across requests.**

- `src/tools/state_store.py`, the `todo` and `memory` tool modules, and their
  skills are removed. Their Action IDs are retired and must not be reused.
- No replacement in-process cache is provided for these capabilities.
- A future tool requiring state across requests must be supplied by the
  caller as an external tool under D-004. The caller owns its store,
  retention policy, and tenant isolation.
- Run-scoped state remains in `ExecutionState`; it is discarded with the
  run. The `SessionManager` remains per-call and is not a persistent store.
- The `data` tool may read a caller-provided SQLite database in read-only
  mode. It does not create or write that database and is not an orchestrator
  persistence mechanism.

## Consequences

**Positive**

- Local tools cannot persist user task or memory data across requests.
- Persistence, retention, and tenant isolation remain at the owning
  application boundary.
- Callers can still offer these capabilities through their own external
  tool definitions and execution.

**Costs**

- Callers that relied on built-in `todo` or `memory` must provide external
  tools to preserve those capabilities.
- The built-in tool registry has two fewer tools.

## Alternatives considered

1. **Keep the SQLite state store.** Rejected: the orchestrator does not own
   the application's persistent data lifecycle.
2. **Replace it with a process-local cache.** Rejected: process restarts
   would silently discard tasks and memories.
3. **Make `todo` and `memory` caller-owned external tools.** Accepted as the
   migration path under D-004.

## Enforcement

- `test_todo_and_memory_are_not_registered` verifies neither tool is in the
  default registry.
- `test_state_store_module_and_imports_are_absent` guards against restoring
  the deleted module or importing it.
- `test_tools_do_not_import_persistence_libraries` guards tool definitions
  against database/store dependencies. `data.py` is excluded because its
  narrowly scoped SQLite feature reads a caller-provided database.
