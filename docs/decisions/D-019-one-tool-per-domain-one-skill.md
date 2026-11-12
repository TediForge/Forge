# D-019: One Tool Per Domain, Operations Inside the Tool, One Skill Per Tool

> **Partially superseded by D-020.** D-019's one-tool-per-domain and
> one-skill-per-tool rules remain in force. D-020 makes `operation` mandatory
> for every registered tool, including single-operation tools, and defines
> the placeholder contract. See [D-020](./D-020-uniform-operation-field.md).

- **Status:** Accepted
- **Date:** 2026-11-10
- **Owner:** Orchestrator
- **Partially supersedes:** D-009 by making the one-tool-per-capability rule concrete for data, image, and video domains and adding enforcement tests.
- **Related:** [D-009](./D-009-one-word-tool-contract.md), [Orchestrator Runtime §9](../architecture/orchestrator-runtime.md), [Skill taxonomy](../references/skills.md)

## Context

D-009 requires one-word public tool names, an `operation` argument for
multi-operation capabilities, and one `SKILL.md` per registered tool. The
implementation drifted in the data domain: `data.py` registered `table`,
`sql`, `profile`, `join`, `report`, and `chart` as six tools, and six skill
folders repeated the common dataset context. Image and video already use one
registered tool and skill apiece, with operations selected by an argument.

The public tool list should represent capabilities, not every internal
handler. Per-operation registration expands the model-visible schema set and
forces duplicated skill guidance.

## Decision

**Register one tool per domain. Put related operations behind its required
`operation` argument and document them in the tool's one skill file.**

- `data` is one tool with operations `table`, `sql`, `profile`, `join`,
  `report`, and `chart`. The implementations remain internal handlers.
- `image` remains one tool with operations `info`, `resize`, `analyze`, `ocr`,
  `detect`, and `generate`.
- `video` remains one tool with operations `probe`, `sample`, and `keyframe`.
- Each registered tool has exactly one matching skill folder containing one
  `SKILL.md`. Its operations table explains required arguments and behavior.
- No skill folder is created for an internal operation.

The tool schema validates the operation and its required arguments before
dispatch. The handler also returns a structured `INVALID_OPERATION` or
`INVALID_ARGUMENTS` result for invalid direct calls.

## Consequences

- The model sees domain-level tools rather than one tool per data operation.
- One skill teaches common context once and documents operation-specific
  arguments, examples, and failure modes.
- The schema union contains more optional parameters, but operation-specific
  conditional requirements keep invalid calls from reaching handlers.
- Renaming the six former data tools to `data(operation=...)` is a breaking
  migration for model prompts; all in-repository callers and tests are
  updated together.
- Internal operation Action IDs remain stable; the selected operation's
  handler owns the emitted Action descriptor.

## Alternatives considered

1. **Keep six registered data tools and six skills.** Rejected because the
   model must choose among verbs for one capability and common guidance is
   repeated.
2. **Keep separate registered tools but share one skill.** Rejected because
   registry loading is keyed by tool name and the model would still see six
   schemas.
3. **Create operation-specific skill folders.** Rejected because operations
   are not independently registered tools.
4. **Rely on tool schemas without skills.** Rejected because usage boundaries
   and edge-case guidance do not fit in the argument schema.

## Enforcement

- `tests/unit/test_one_skill_per_tool.py` requires exact equality between
  registered tool names and tool skill folders, and exactly one Markdown
  skill file in each folder.
- The same test compares `data`, `image`, and `video` operation schemas with
  the operations listed in each skill's operations table.
- Registry tests assert the six former data operation names are no longer
  registered tools.

## Implementation

- `src/tools/definitions/data.py` registers only `data`; table, SQL, profile,
  join, report, and chart handlers are private dispatch targets.
- `src/tools/definitions/image.py` and `video.py` remain one tool each.
- `src/skills/tools/data/SKILL.md` contains the data operations table and
  shared usage guidance; the former operation-named skill folders are
  removed.
- See also [Orchestrator Runtime §9](../architecture/orchestrator-runtime.md)
  and the [Skill taxonomy](../references/skills.md), plus
  [D-020](./D-020-uniform-operation-field.md).
