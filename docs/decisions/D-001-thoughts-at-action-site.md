# D-001: Assign Thought and Action IDs at Their Emission Sites

- **Status:** Accepted
- **Date:** 2026-11-09
- **Owner:** Orchestrator
- **Related:** [Thought and Action Contract](../references/thought-contract.md), [Thought IDs](../references/thought-ids.md), [Action IDs](../references/action-ids.md)

## Context

The registry previously required construction-time `THOUGHT_IDS` metadata while
handlers independently emitted literal IDs. This duplicated identity data,
allowed the two declarations to drift, and could prevent engine construction
because of an optional adapter's missing metadata.

## Decision

IDs are declared beside the code that emits the corresponding event. Thought
IDs are literals at the reasoning/progress emission site. Local tool Action
IDs are attached to their handler with `action_handler(...)`; integration
Action IDs and descriptors are returned by that integration's `actionFor()`.
The registry stores schemas and handlers only and does not require, store, or
validate event IDs during construction.

The ID documents are compatibility catalogs, not runtime lookup tables. Tests
validate ID shape, uniqueness, and presence in the appropriate catalog.

## Consequences

- An optional integration without credentials or runtime initialization no
  longer blocks registry or engine construction.
- Handler code owns each event descriptor; the catalog is synchronized by
  tests.
- Consumers must not depend on registry methods for Thought or Action IDs.

## Alternatives considered

- Add another module-level ID map: rejected because it retains duplicate
  sources of truth.
- Invoke handlers during registry construction: rejected because handlers
  may perform network or file operations and require runtime inputs.
- Parse handler source with AST at runtime: rejected as unnecessary runtime
  complexity; tests are sufficient.
