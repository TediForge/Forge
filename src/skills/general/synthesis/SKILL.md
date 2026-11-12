---
name: synthesis
description: Produce the final user-facing answer by integrating execution results, evidence, citations, and multimodal outputs.
category: general
version: 1.0
---

# Title
Response Synthesis Skill

## Overview
Turn completed or partial execution results into a coherent, accurate response tailored to the user's request.

## When to use this skill
- Results come from multiple skills, tools, models, or execution steps.
- The final response needs ranked evidence, citations, status, or multimodal assets.
- A streamed run must end with a complete response consistent with the final static shape.

## When NOT to use this skill
- A single tool or skill already produced the final answer in the requested format.
- The task only needs raw structured data with no user-facing explanation.

## Steps
1. Gather completed outputs, source references, safe progress events, status, and relevant constraints.
2. Resolve contradictions and prioritize direct, reliable, objective-relevant evidence.
3. Compose a direct answer, attach citations to supported claims, and include relevant limitations.
4. Include media assets and execution status using the response schema.
5. For streaming, preserve event order and finish with a complete payload consistent with static output.

## Guidelines
- Do not expose private chain-of-thought, secrets, internal credentials, or unsafe raw tool data.
- Do not fabricate citations, media, completion status, or results for failed steps.
- Distinguish completed work from partial results and explain material uncertainty.
- Keep source ranking and response length proportional to the user's decision.

## Input
User objective, execution outputs, trusted citations, media assets, status, and response-format requirements.

## Output
A schema-valid final answer with relevant citations/assets, safe progress summaries, and accurate terminal status.

## Examples
Input: Results from two research tools and a document extractor.
Output: A concise synthesis that reconciles the findings, cites each source, and flags extraction uncertainty.

## Edge cases
- If sources disagree, present the disagreement and basis for weighting rather than hiding it.
- If execution stops early, summarize verified partial results and state what remains incomplete.

## Notes (optional)
This skill describes synthesis policy; response serialization and SSE framing remain in `src/synthesis`.