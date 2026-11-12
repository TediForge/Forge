---
name: refiner
description: Refine a user's request into a precise execution prompt while preserving intent and making assumptions explicit.
category: general
version: 1.0
---

# Title
Prompt Refinement Skill

## Overview
Improve task clarity and execution readiness without changing what the user asked for.

## When to use this skill
- The original request is shorthand, underspecified, or needs a domain-specific acceptance target.
- Planning or generation benefits from a self-contained prompt and explicit constraints.

## When NOT to use this skill
- The prompt is already precise and refinement would add noise.
- Missing information requires a user decision rather than a safe, stated assumption.

## Steps
1. Preserve the user's objective, named entities, constraints, and requested deliverable.
2. Use intent and attachment context to select a relevant domain profile.
3. Add only useful audience, format, validation, and acceptance details.
4. Record material ambiguity and return the expected structured refinement.

## Guidelines
- Never invent requirements, facts, data, or permissions.
- Keep the original request available alongside the refined version.
- Make assumptions visible and conservative; ask when an assumption would change outcomes.
- Avoid turning a simple task into a multi-step workflow without need.

## Input
Original user request, classified intent, attachment context, and applicable constraints.

## Output
A structured refined prompt with objective, modality profile, constraints, acceptance criteria, and ambiguity flags.

## Examples
Input: "Make this faster."
Output: A refinement that requests measurable performance improvement and validation while flagging the missing workload/latency target.

## Edge cases
- If provider output is malformed, return a deterministic, intent-preserving refinement.
- If the target cannot be inferred without changing scope, flag the ambiguity instead of guessing.

## Notes (optional)
Refinement prepares execution; it does not authorize actions or replace user approval.