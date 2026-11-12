---
name: fetch
description: Use to retrieve text, JSON, or PDF content from an allowlisted HTTPS URL; do not use for web discovery or untrusted local paths.
category: tool
---

# Fetch

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `url` | Fetch readable text from a page | `url` | implemented |
| `pdf` | Fetch and extract PDF text | `url` | implemented |
| `json` | Fetch and parse JSON data | `url` | implemented |

## When to use
- The user provides a known HTTPS URL and asks to retrieve its contents.
- The user provides a JSON endpoint or a PDF URL for inspection.
- The hostname is explicitly allowlisted by the deployment.

## When not to use
- Do not use for current web discovery; use `search(operation="web")`.
- Do not use for local files; use `pdf` or `sheet`.
- Do not use for hosts outside the configured HTTPS allowlist.

## How to call
Call `fetch(operation="url"|"pdf"|"json", url="https://...")`. Retrieval is bounded to 5 MB, redirects are disabled, and only configured HTTPS hosts are allowed.

## Examples
1. Page text: `fetch(operation="url", url="https://docs.example.org/guide")`.
2. PDF: `fetch(operation="pdf", url="https://docs.example.org/report.pdf")`.
3. JSON: `fetch(operation="json", url="https://api.example.org/status")`.
4. For discovery, use `search(operation="web")`, not this fetch tool.
5. Wrong operation returns `INVALID_OPERATION`; choose one of the listed formats.

## Edge cases
- **Host not allowlisted:** report `HOST_NOT_ALLOWED`; do not retry an alternate host.
- **Unknown operation:** report `INVALID_OPERATION`.
- **Invalid URL:** report the URL validation error; do not downgrade to HTTP.
- **Non-text response:** report `UNSUPPORTED_CONTENT_TYPE`.
- **Oversized content:** report the size-limit error; do not summarize partial data.
- **Provider unavailable:** do not retry an unimplemented operation.
- **Empty response:** report `EMPTY_CONTENT`; do not invent page text.
