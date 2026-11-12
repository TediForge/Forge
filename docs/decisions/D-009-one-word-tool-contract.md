# D-009: One-Word Tool Names and Mandatory Tool Skills

> **Partially superseded by D-019.** The one-word name rule and mandatory
> skill requirement remain in force. D-019 clarifies the concrete
> data/image/video domain-operation shape and adds enforcement tests. Where
> D-009 is abstract, D-019 is the authoritative interpretation. See
> [D-019](./D-019-one-tool-per-domain-one-skill.md).

- **Status:** Accepted
- **Date:** 2026-11-09
- **Owner:** Orchestrator
- **Related:** [Orchestrator Runtime §9](../architecture/orchestrator-runtime.md), [Tool skills](../../src/skills/tools/)

## Context

Tool names have mixed action and service identifiers, and the registry has no
consistent place to explain when a tool should or should not be used. This
causes avoidable choice ambiguity and makes service-specific guidance difficult
to discover without overloading schemas.

## Decision

Every registered tool name MUST match `^[a-z][a-z0-9]*$`. Names describe the
action, not the service. Renames have no compatibility aliases. Tools that
offer multiple operations use one public name with an `operation` argument.

Every registered tool MUST have a `src/skills/tools/<name>/SKILL.md` file. Its YAML
frontmatter declares the matching name, a nonempty trigger description, and
`category: tool`; its body explains when to use and not use the tool, how to
call it, output expectations, and edge cases. Agent and general skills are
categorized under `src/skills/agents/` and `src/skills/general/` respectively.

The registry validates both tool-name syntax and the associated tool skill
before accepting registration. CI tests assert the rule over the assembled
registry. Skill loading validates frontmatter and loads agent prompts lazily
per instance, with an explicit reload method for development.

## Consequences

- Tool-name changes are breaking migrations; callers, schemas, Action
  descriptors, tests, and docs are updated together.
- Consolidated integration operations retain service context in their skills,
  parameter schemas, and Action metadata rather than public tool names.
- Skill authoring and maintenance are part of changing a tool contract.
- Existing Action IDs remain stable across public-name migrations.

## See also

- [D-019: One tool per domain, operations inside the tool, one skill per tool](./D-019-one-tool-per-domain-one-skill.md)
- [D-020: `operation` is mandatory on every tool](./D-020-uniform-operation-field.md)
