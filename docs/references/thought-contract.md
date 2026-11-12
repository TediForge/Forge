# Thought and Action Contract

## Purpose

A Thought is user-visible reasoning or progress intent, never private
chain-of-thought and never an execution record. Its stable `T` ID is assigned
where that reasoning/progress event is emitted and listed in
[thought-ids.md](thought-ids.md).

## Wire contract

Public JSON field names are camelCase. The only deliberate snake_case
exception is `call_id` on `FunctionCall`, which OpenAI Responses clients expect.
Python field names are internal; `CamelBaseModel` and `to_camel` define the
wire aliases. New public fields must use camelCase before merge. See the
[wire contract](wire-contract.md).

An Action records a tool, integration, or data operation. Its stable `A` ID is
owned by the action handler and listed in [action-ids.md](action-ids.md).
The registry does not store Thought or Action IDs. During the one-release
migration window, tool Actions also emit a deprecated legacy Thought with
`data.deprecated: true`; clients should migrate to Action events.

## Thought shape

```json
{
  "id": "T9N3Q7",
  "type": "thought",
  "message": "Reviewing progress before continuing",
  "status": "processing",
  "data": {"stepId": 2}
}
```

| Field | Contract |
| --- | --- |
| `id` | Stable `T` plus five uppercase alphanumeric characters; literal at the Thought emission site |
| `type` | Literal `thought` |
| `message` | Concise user-safe progress or reasoning summary |
| `status` | `started`, `processing`, or `completed` |
| `data` | Structured JSON details; never private chain-of-thought |

## Action shape

```json
{
  "type": "action",
  "runId": "run_abc123",
  "sequence": 4,
  "data": {
    "actionId": "A5Q8V3",
    "actionType": "integration",
    "toolName": "canva_create_design",
    "status": "processing",
    "message": "Creating a Canva design",
    "startedAt": "2026-11-09T14:02:11.001Z",
    "endedAt": null,
    "metadata": {"designType": "poster"}
  }
}
```

`actionType` is `tool`, `integration`, `data`, or `attachment`. `status`
transitions through `started`, `processing`, and `completed` or `failed`.
Failed events may include a machine-readable error code and a user-safe
message, never raw exception text. Action metadata is optional; do not include
raw arguments or results. Apply the audit redaction helper to any structured
metadata before emitting it.

## Status shape

```json
{
  "type": "status",
  "runId": "run_abc123",
  "sequence": 7,
  "data": {
    "status": "completed",
    "terminationReason": "plan_exhausted",
    "startedAt": "2026-11-09T14:02:00.000Z",
    "endedAt": "2026-11-09T14:02:18.412Z",
    "stepCount": 3,
    "toolCallCount": 2
  }
}
```

Run statuses are `started`, `planned`, `completed`, `failed`, and `cancelled`.
`terminationReason` is the execution budget's reason when present.

## Stream envelope

The top-level stream types are `thought`, `action`, `status`, `textChunk`, and
`complete`. All events have a `runId` and monotonically increasing `sequence`.
The terminal `complete` payload mirrors the static response and contains one
ordered `events` timeline and ordered `content` blocks.

During the compatibility release only, a tool operation may also emit a
legacy Thought using its former `T`-prefixed Action ID. Such an event must
include `data.deprecated: true` and the replacement `actionId`. It is not a
reasoning Thought and must not be added to the reasoning-only ID catalog.

## Thought IDs

| ID | Contract |
| --- | --- |
| `T4P8M2` | General progress: `{stepId?: integer, detail?: string}` |
| `T9N3Q7` | Analysis/execution progress: `{stepId?: integer, modality?: string, decision?: string, reason?: string}` |
| `T6D2V9` | Planning: `{stepCount?: integer, capabilities?: string[]}` |
| `T0A1B2` | Synthesis/media preparation: `{mediaType?: "image"|"video"|"audio", assetId?: string}` |

## Security and evolution

Never expose private message bodies, credentials, file bytes, raw model
reasoning, or raw exceptions through Thought or Action data. Keep the action
ID catalog synchronized with handler-owned IDs in CI. Breaking changes to the
event envelope require a new decision record and a documented client migration
window.
