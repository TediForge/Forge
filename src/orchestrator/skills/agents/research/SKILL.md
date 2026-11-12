---
name: research
description: Perform evidence-grounded research when a request needs current facts, investigation, comparison, or source-backed conclusions.
category: agent
version: 1.0
---

# Title
Research Skill

## Overview
Investigate a question systematically and produce a concise answer supported by reliable sources.

## When to use this skill
- The request asks for research, fact-finding, comparison, or current information.
- The answer depends on claims that should be verified against external sources.

## When NOT to use this skill
- The user asks for a direct code change or a self-contained explanation that needs no external evidence.
- The task is primarily creative writing or summarizing only supplied material.

## Steps
1. Restate the question as answerable sub-questions and identify what may have changed recently.
2. Search primary sources first, then use reputable secondary sources to add context or cross-check.
3. Compare evidence, resolve disagreements where possible, and note uncertainty or missing coverage.
4. Present the conclusion with citations adjacent to the claims they support.

## Guidelines
- Prefer official documentation, original research, legislation, standards, and first-party data.
- Verify dates, version numbers, and scope before treating a source as current.
- Distinguish sourced facts from analysis and recommendations.
- Never fabricate sources, quotations, or certainty; state when evidence is incomplete.

## Input
A research question, topic, constraints, audience, and any required date range or source preferences.

## Output
A direct conclusion, supporting evidence with links, relevant caveats, and unresolved questions when needed.

## Examples
Input: "Compare the current supported Python versions for these libraries."
Output: A concise comparison based on each library's official support documentation, with checked dates.

## Edge cases
- If sources conflict, explain the conflict and prioritize the most authoritative, recent evidence.
- If browsing is unavailable, state that current claims could not be verified and avoid implying otherwise.

## Notes (optional)
Keep the answer proportional to the decision the research is meant to support.
