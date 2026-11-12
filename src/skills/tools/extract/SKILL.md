---
name: extract
description: Use to parse supplied JSON, XML, YAML, or CSV text; do not use for extracting facts from ordinary prose.
category: tool
version: 1.0
---

# Extract

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `json` | Isolate and validate embedded JSON | `text`, `schema` | implemented |
| `xml` | Parse bounded XML text | `text` | implemented |
| `yaml` | Parse safe YAML text | `text` | implemented |
| `csv` | Parse bounded CSV text | `text` | implemented |

## Overview
`extract` locates a JSON value already present in text and returns it only if it validates against the supplied schema. It does not infer or generate missing values.

## When to use
- The user supplies text containing a JSON payload that must be validated or isolated.
- A tool or document embeds structured JSON among surrounding prose.
- The user supplies XML, YAML, or CSV text and requests parsing.

## When not to use
- Do not use for natural-language entity extraction; no language model is called.
- Do not use to repair malformed JSON or invent fields.
- For arithmetic or tabular processing, use `calculate` or the matching `data` operation.
- Do not use for local files; use `sheet`, `pdf`, or `fetch`.
- Do not use to infer entities from ordinary prose.

## Procedure and call
Call `extract(operation, text)` for XML/YAML/CSV. JSON additionally requires a JSON Schema. Inputs are bounded to 100,000 characters; CSV rows are capped at 500.

## Output
Success returns `{success, data, source, error: null, errorCode: null}`. Failure returns `success: false`, `data: null`, a short `error`, and an `errorCode` such as `NO_JSON`, `NO_MATCH`, or `INVALID_SCHEMA`.

## Guidelines
- Preserve the supplied schema; do not weaken it to force a match.
- Confirm missing or conflicting fields with the user rather than guessing.
- Input is limited to 100,000 characters and schema JSON to 32,000 characters.

## Examples
1. **Validate an embedded object:** Text says `Payload: {"id": 7}`; schema requires integer `id`; return that object.
2. **Ignore surrounding prose:** A log line contains `result={"ok":true}`; extract the object if the schema permits it.
3. **Choose a schema match:** Text contains multiple JSON fragments; return the first one satisfying the requested schema.
4. **Do not infer prose:** Text says “the order number is 7” with no JSON; return `NO_JSON`.
5. **Adjacent-tool boundary:** A CSV requiring aggregation belongs to `data(operation="table")`, not `extract`.
6. **XML:** `extract(operation="xml", text="<order id='3'><item>book</item></order>")`.
7. **YAML:** `extract(operation="yaml", text="name: Ada\ncount: 2")`.
8. **CSV:** `extract(operation="csv", text="name,count\nAda,2")`.
9. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`; choose one of the four listed formats.

## Edge cases
- **No JSON candidate:** report `NO_JSON`; never synthesize one.
- **Schema mismatch:** report `NO_MATCH`; preserve the source text.
- **Invalid schema:** report `INVALID_SCHEMA`; do not silently substitute `{}`.
- **Oversized text:** report `TEXT_TOO_LARGE`; do not truncate and claim completeness.
- **Malformed or nested JSON:** ignore invalid candidates and return a clear failure if none validate.
- **XML DTD/entity declarations:** rejected with `INVALID_XML`.
- **YAML anchors/aliases:** rejected to keep parsing bounded.
- **CSV row cap:** report `TOO_MANY_ROWS`; do not claim the result is complete.
- **Wrong format:** report the parser error rather than treating content as another format.
