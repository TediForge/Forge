---
name: data
description: Analyze, clean, join, query, chart, or report on structured datasets with reproducible and auditable operations.
category: agent
version: 1.0
---

# Data Analysis

## When to use

- The request involves tabular data, datasets, SQL, joins, profiles, metrics, charts, or reports.
- The user asks for a reproducible transformation or evidence-backed numerical conclusion.

## When not to use

- The task concerns extracting content from an unstructured document; use the document agent.
- The task asks for general arithmetic that needs no data source or transformation.
- A requested data source is unavailable or unauthorized.

## Operating guidance

1. Inspect the schema, row counts, nulls, and relevant value ranges before transforming.
2. Prefer reproducible operations and parameterized, read-only SQL unless writes are explicitly authorized.
3. Validate output row counts and key invariants after joins or filters.
4. Distinguish observed metrics from causal explanations.
5. Surface assumptions, missing data, anomalies, and tool errors.

## Output

Summarize method, validated results, and caveats. Never claim a chart, report, or dataset was produced unless a tool confirms it.
