---
name: evaluator
description: Assess execution progress and recommend whether the orchestrator should continue, summarize, or stop.
category: general
version: 1.0
---

# Title
Execution Evaluation Skill

## Overview
Evaluate whether recent execution results make measurable progress toward the user's objective and choose a bounded next action.

## When to use this skill
- After an execution step or iteration produces new output.
- When the orchestrator must detect repetition, stalled progress, or completion.

## When NOT to use this skill
- To replace authorization, policy checks, approval gates, or execution budgets.
- When there is no execution output to evaluate.

## Steps
1. Compare recent outputs with the objective and acceptance criteria.
2. Detect repeated results, dead ends, missing evidence, and diminishing progress.
3. Recommend `continue`, `summarize`, or `stop` with a concise rationale and progress score from 0 to 1.
4. Prefer summarizing useful partial results when further execution is unlikely to help.

## Guidelines
- Base the decision on observed outputs, not assumed progress.
- Do not claim completion unless the objective is supported by evidence.
- Never override hard limits, safety policy, authorization, or required approvals.
- Keep the rationale concise and identify material unmet criteria.

## Input
The objective, recent execution outputs, and optional prior progress scores.

## Output
JSON with `decision`, `progress_score`, and `reasoning` fields.

## Examples
Repeated identical tool results should recommend `stop`; changed results that address remaining criteria can recommend `continue`.

## Edge cases
- With fewer than two outputs, recommend `continue` with a neutral score unless an independent completion signal exists.
- When evidence is mixed, recommend `summarize` rather than asserting success.

## Notes (optional)
This skill advises the Responses execution loop; it is not an autonomous agent and does not execute tools.