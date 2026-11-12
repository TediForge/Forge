---
name: classifier
description: Classify a request by intent, modalities, primary capability, tool needs, and execution complexity before planning.
category: general
version: 1.0
---

# Title
Intent Classification Skill

## Overview
Convert a user request into a compact, schema-valid intent description that supports reliable planning.

## When to use this skill
- A request must be routed to one or more modalities or capabilities.
- The orchestrator needs to decide whether tools or sequential execution are required.

## When NOT to use this skill
- The task is already explicitly routed and classification would not change execution.
- The request is only asking for a final response with no planning or tool selection.

## Steps
1. Identify the user's objective and relevant attachments or conversation context.
2. Select all required modalities and one primary capability.
3. Set tool and multi-step flags based on actual task dependencies, not broad topic labels.
4. Return only fields allowed by the intent schema and preserve the original objective.

## Guidelines
- Distinguish capability from modality; for example, coding is a capability that may use text and tools.
- Mark tools only when external or executable actions are necessary.
- Mark multi-step execution when later work depends on earlier outputs.
- Do not infer access to a service, integration, or attachment that is not available.

## Input
The user request plus relevant attachment names, conversation context, and available capability information.

## Output
Schema-valid intent data: brief reasoning, modalities, primary capability, tool/multistep flags, and normalized prompt.

## Examples
Input: "Summarize this image of a receipt."
Output: Vision/document analysis with a text summary; no external tools unless required by the runtime.

## Edge cases
- For ambiguous requests, choose the most conservative useful capability and retain uncertainty in the reasoning field.
- For unsupported modalities, identify the limitation rather than assigning a nonexistent model.

## Notes (optional)
Classification is routing metadata, not a user-facing answer.