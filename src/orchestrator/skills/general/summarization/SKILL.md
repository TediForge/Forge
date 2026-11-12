---
name: summarization
description: Condense documents, conversations, or evidence while preserving key claims, decisions, caveats, and attribution.
category: general
version: 1.0
---

# Title
Summarization Skill

## Overview
Reduce source material to its decision-relevant content without changing meaning or overstating evidence.

## When to use this skill
- The user requests a summary, brief, abstract, recap, or extraction of key points.
- A larger body of supplied or retrieved material needs to be made easier to scan.

## When NOT to use this skill
- The user needs new research, a recommendation requiring independent analysis, or a creative rewrite.
- The request requires preserving every detail, such as a complete transcript or legal text.

## Steps
1. Identify the requested audience, length, purpose, and source boundaries.
2. Extract the main conclusion, supporting points, decisions, actions, and material caveats.
3. Group related details and remove repetition while preserving important distinctions.
4. Check the summary against the source for omissions, unsupported claims, and attribution.

## Guidelines
- Do not introduce facts absent from the source unless clearly labeled as context.
- Preserve uncertainty, disagreement, chronology, and responsibility when they affect meaning.
- Prioritize conclusions and actions over incidental detail.
- Cite or identify source sections when traceability is requested or useful.

## Input
Source material and any requested audience, length, focus, format, or exclusion criteria.

## Output
A proportionate summary with key points, decisions or actions, and caveats where relevant.

## Examples
Input: "Summarize this incident report for the engineering lead."
Output: A short recap of impact, cause, remediation, remaining risk, and owner/action items.

## Edge cases
- If the source is incomplete or internally inconsistent, state that limitation.
- If there is no clear conclusion, summarize the competing positions rather than forcing one.

## Notes (optional)
Use the requested level of detail; a summary is not automatically a one-paragraph response.
