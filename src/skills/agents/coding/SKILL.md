---
name: coding
description: Implement, debug, review, or refactor software while preserving project conventions and validating behavior.
category: agent
version: 1.0
---

# Title
Coding Skill

## Overview
Make focused, maintainable software changes grounded in the existing codebase and verified with relevant checks.

## When to use this skill
- The task requires implementing or changing code, tests, configuration, or technical documentation.
- The user asks to diagnose a defect, review a change, or improve a code path.

## When NOT to use this skill
- The request is solely for research, prose composition, or a conceptual explanation with no codebase changes.

## Steps
1. Locate the owning code path, nearby conventions, tests, and applicable repository instructions.
2. Form a testable hypothesis and choose the smallest relevant change.
3. Implement the change without disturbing unrelated user work.
4. Run the narrowest check that can falsify the hypothesis, then any required broader gate.
5. Summarize changed behavior and disclose checks that could not be run.

## Guidelines
- Fix causes rather than symptoms; preserve public interfaces unless the request requires a change.
- Keep scope small and reuse project abstractions and test helpers.
- Do not claim tests pass unless they were run; distinguish existing failures from new regressions.
- Never expose secrets or perform destructive repository operations without explicit authorization.

## Input
A change request, bug report, review target, or codebase question with relevant paths and constraints.

## Output
The requested implementation or analysis, focused validation results, and any material caveats.

## Examples
Input: "Fix the parser error for empty input."
Output: A minimal parser fix with a regression test and its focused test result.

## Edge cases
- If architecture or requirements are underspecified, inspect local evidence and ask only for decisions that block safe implementation.
- If validation fails for an unrelated baseline issue, report it without broadening the patch unnecessarily.

## Notes (optional)
Prefer reversible changes when the controlling behavior is not yet fully understood.
