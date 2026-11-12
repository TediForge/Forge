# Skills

Skill files live under `src/skills/`. This keeps them within the orchestrator
package and lets the loader resolve them relative to `src/skills/loader.py`.
Every file is named `SKILL.md` and begins with YAML frontmatter containing
`name`, `description`, and `category`.

## Categories

| Category | Location | Purpose |
|---|---|---|
| Tool | `src/skills/tools/<name>/SKILL.md` | How and when to call one registered local tool |
| Agent | `src/skills/agents/<name>/SKILL.md` | How one specialist agent performs its job |
| General | `src/skills/general/<name>/SKILL.md` | Classifier, planner, refiner, evaluation, and other engine guidance |

Directory names are lowercase one-word identifiers. Agent prompts are loaded
lazily through `BaseAgent.system_prompt`; tool skills are checked when the
registry registers a tool. General skills are loaded by engine helpers.

External tools are caller-owned, so their skills do not belong in this tree.
See [Caller-Owned External Tools](./external-tools.md).

## Quality standard

Every skill has:

- Valid frontmatter: `name`, `description`, `category`, and preferably `version`.
- A description that says when to use the skill and when not to use it.
- An overview, concrete use/non-use triggers, an ordered procedure, guidelines,
  expected input and output, examples, and edge cases.
- At least five examples in the format below, including an over-use case and a
  boundary example with an adjacent tool, agent, or general skill.
- At least five named edge cases and the correct response for each.

Tool skills document the exact signature, required/optional arguments, output
shape, and errors. Agent skills preserve their behavioral instructions and
document procedure and handoff conditions. General skills document their
structured decision or output contract. Keep each skill concise and move
reference material into a nearby `references/` directory when appropriate.
For multi-operation tools, keep all operations in the single skill whose
directory matches the registered tool name; do not create operation-named
skill folders.

## One tool, one skill, operations inside

A tool is a domain capability, not each of its internal functions. `data` is
one tool with operations `table`, `sql`, `profile`, `join`, `report`, and
`chart`. `image` is one tool with operations `info`, `resize`, `analyze`,
`ocr`, `detect`, and `generate`. `video` is one tool with operations `probe`,
`sample`, and `keyframe`.

Each registered tool has one skill folder and one `SKILL.md`. The file
contains an operations table, argument guidance, examples, and edge cases.
There is no `skills/tools/table/`, `skills/tools/profile/`, or other
operation-named folder. Enforcement lives in
`tests/unit/test_one_skill_per_tool.py`. See
[D-019](../decisions/D-019-one-tool-per-domain-one-skill.md).

**`operation` is mandatory on every tool.** A one-capability tool has a
single-value enum (`clock(operation="now")`,
`calculate(operation="evaluate")`); a multi-capability tool has a multi-value
enum. A placeholder returns `NOT_IMPLEMENTED`. The skill table lists every
operation with a Status (`implemented` or `placeholder`). See
[D-020](../decisions/D-020-uniform-operation-field.md).

Example structure:

```markdown
### 1. Empty result

**Poor input:** A request with no search terms.

**Failure mode:** The tool is called with an empty query and produces noise.

**Correct behavior:** Ask for the missing subject or use the known context;
do not fabricate query terms.
```

The reference implementation for prompt refinement is
`src/skills/general/refiner/SKILL.md`. Skills are executable behavior
specifications and should be reviewed as code.

## Promotion rule

`general/` is the catch-all for skills that are neither tool nor agent skills.
A new top-level category requires a decision record that defines and migrates
the category. Do not introduce ad-hoc `misc/`, `other/`, or workflow folders.
