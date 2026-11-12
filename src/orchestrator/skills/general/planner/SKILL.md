---
name: planner
description: Build a minimal ordered execution plan with explicit dependencies, capabilities, and available tools.
category: general
version: 1.0
---

# Title
Execution Planning Skill

## Overview
Translate classified intent into an actionable plan that meets the objective with the fewest necessary steps.

## When to use this skill
- Intent requires multiple operations, tools, integrations, or modality transitions.
- A task needs explicit sequencing or dependency tracking.

## When NOT to use this skill
- A single direct response can satisfy the request without tools or dependent work.
- The task is still unclear enough that planning would require inventing requirements.

## Steps
1. Review the intent, context, active integrations, constraints, and available capabilities.
2. Break the objective into executable steps and identify data dependencies.
3. Assign each step a valid modality, capability, instruction, and only the tools it needs.
4. Verify step identifiers and dependency edges, then return the required plan schema.

## Guidelines
- Prefer the smallest complete plan; avoid duplicate research or unnecessary preparation steps.
- Dependencies must reference prior step identifiers and represent actual information flow.
- Do not request tools or integrations that are unavailable or inactive.
- Preserve safety, approval, and authorization boundaries in the plan.

## Input
Classified intent, request context, active integrations, available capabilities, and execution constraints.

## Output
Schema-valid ordered plan with reasoning, sequencing, and explicit step dependencies.

## Examples
Input: A request to create an issue from an incident report.
Output: First extract the issue details; then create the issue using the authorized integration.

## Edge cases
- If an integration is not active, plan a clarification or explain the missing prerequisite rather than attempting the action.
- If steps are independent, do not add artificial dependencies.

## Notes (optional)
The execution engine remains responsible for enforcing budgets, policies, and approval gates.