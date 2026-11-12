---
name: data
description: Use to inspect, profile, filter, join, query, report, or chart CSV/SQLite data; do not use for media files or conceptual questions.
category: tool
version: 1.0
---

# Data

Use this single tool for local CSV and SQLite dataset tasks. Select one domain
operation; do not call a separate tool named after the operation.

## Operations

| operation | What it does | Required arguments | Status |
|---|---|---|---|
| `table` | Inspect a CSV with `profile`, `head`, `describe`, `groupby`, `filter`, `shape`, or `columns` | `path`, `options` (`options.operation` required) | implemented |
| `sql` | Run a parameterized, read-only SQLite query | `connection`, `query` | implemented |
| `profile` | Report CSV columns, types, missing values, and duplicate rows | `path` | implemented |
| `join` | Join two CSV files by key | `left_path`, `right_path`, `left_key` | implemented |
| `report` | Compile supplied sections to Markdown, HTML, JSON, or CSV | `title`, `sections` | implemented |
| `chart` | Create a PNG chart from a CSV | `path`, `chart_type`, `x_column`; `y_column` for line, bar, or scatter | implemented |

All paths must stay inside the configured data directory. `table` options may
include `rows`, `column`, `equals`, `limit`, `aggregate`, and `value_column`.
`join_type` is `inner`, `left`, `right`, or `outer`. Reports accept
`format` (`markdown`, `html`, `json`, or `csv`) and optional `output_path`.
Charts accept `line`, `bar`, `histogram`, or `scatter`; `output_path` defaults
to `outputs/chart.png`.

## When to use

- The user asks to inspect, profile, filter, aggregate, or join a CSV.
- The user asks a question answerable from a local SQLite database.
- The user asks to render a chart or compile already available findings.

## When not to use

- Image, audio, or video files: use `image`, `audio`, `transcribe`, or `video`.
- PDF text extraction: use `pdf(operation="text")`.
- A conceptual question with no dataset: answer directly; do not invent data.
- A database write: SQL is read-only; explain that writes are not supported.

## How to call

Call `data(operation, ...)` with the required arguments from the table. Use
`table` for basic CSV exploration, `profile` for a dedicated data-quality
summary, and `sql` for complex read-only SQLite analysis.

## Examples

1. **Profile:** `data(operation="profile", path="uploads/sales.csv")`.
2. **Preview rows:** `data(operation="table", path="uploads/sales.csv", options={"operation":"head","rows":5})`.
3. **Filter:** `data(operation="table", path="uploads/sales.csv", options={"operation":"filter","column":"region","equals":"West"})`.
4. **Read-only SQL:** `data(operation="sql", connection="sqlite:analytics.db", query="SELECT region, SUM(amount) FROM sales GROUP BY region")`.
5. **Join:** `data(operation="join", left_path="uploads/customers.csv", right_path="uploads/orders.csv", left_key="customer_id", join_type="left")`.
6. **Report:** `data(operation="report", title="Quarterly results", sections=[{"title":"Revenue","content":"Revenue grew 8%."}], format="markdown")`.
7. **Chart:** `data(operation="chart", path="uploads/sales.csv", chart_type="bar", x_column="region", y_column="amount", output_path="outputs/sales.png")`.
8. **Boundary:** for a chart image generated from a dataset, use `chart`; use `image` only to inspect or transform image files.
9. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`; select one of the six listed operations.

## Edge cases

- **Missing required argument:** provide the operation's required arguments; do not guess a column or path.
- **Unknown operation:** choose one of the six domain operations above.
- **Unknown CSV column or join key:** report the returned error and inspect columns before retrying.
- **Write SQL:** only `SELECT`, `WITH`, and query-only `PRAGMA` are allowed; never retry a rejected write query.
- **Empty dataset:** report the measured empty shape or profile without inferring data quality.
- **Outside data directory:** report `PATH_NOT_ALLOWED`; do not try a different path silently.
- **Chart without a y column:** line, bar, and scatter require `y_column`; histogram uses only `x_column`.
- **CSV formula-leading values:** exported formula-like cells are escaped; mention this if relevant.
- **Missing dependency or malformed file:** surface the tool error; do not present partial results as complete.
