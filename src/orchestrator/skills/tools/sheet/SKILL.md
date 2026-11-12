---
name: sheet
description: Use to read, inspect, or write sandboxed CSV data; do not use for SQLite or general data analysis.
category: tool
version: 1.0
---

# Sheet

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `read` | Read bounded CSV headers and rows | `path` | implemented |
| `write` | Write rows to a CSV file | `path`, `headers`, `rows` | implemented |
| `info` | Inspect CSV headers and row count | `path` | implemented |

## When to use
- The user asks to inspect a CSV or create/export a CSV file.
- The user requests CSV header and row-count metadata.
- A bounded row preview is enough to answer a simple CSV question.

## When not to use
- Use `data` for profile, filter, aggregation, or visualization operations.
- Do not write unless the user requested a file or export.
- Do not use for SQLite queries; use `data(operation="sql")`.
- Do not use for profiling, joins, or charts; use the matching `data` operation.

## How to call
`sheet(operation, path, ...)`: `read` takes optional `delimiter` and `maxRows`; `write` requires `headers` and `rows`; `info` counts rows and returns headers.

## Output and edge cases
Paths are restricted to the configured data directory. Reads return headers, rows, and row count; writes return the saved path and row count. Writes escape formula-leading cells. Confirm row counts and never silently truncate beyond the requested/read cap.

## Examples
1. **Inspect a CSV:** Call `sheet(operation="read", path=...)` for a bounded preview.
2. **Custom delimiter:** Specify a one-character delimiter only when the file uses it.
3. **Export rows:** Call `sheet(operation="write", path=..., headers=..., rows=...)` only when requested.
4. **Analysis:** Use `data(operation="table", ...)` for profile, filtering, or aggregation rather than reading a large file manually.
5. **Adjacent-tool boundary:** Use `data(operation="sql", ...)` for SQLite; `sheet` handles CSV files.
6. **Info:** `sheet(operation="info", path="uploads/sales.csv")` returns headers and total data rows.
7. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`; choose `read`, `write`, or `info`.

## Edge cases
- **Missing file:** report `NOT_FOUND`.
- **Invalid delimiter:** provide exactly one character.
- **Missing write data:** require both `headers` and `rows`.
- **Formula-leading values:** note that values are escaped to prevent spreadsheet formula execution.
- **Read cap:** state the returned row count and that the preview may be bounded.
- **Info on empty CSV:** return an empty header list and zero data rows.
- **Read cap:** state the returned row count and that the preview may be bounded.
