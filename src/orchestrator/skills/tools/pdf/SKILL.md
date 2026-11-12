---
name: pdf
description: Use to extract bounded text from sandboxed PDF files; do not use for table or image extraction.
category: tool
---

# PDF

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `text` | Extract bounded PDF text | `path` | implemented |

## When to use
- The user asks for readable text from a local PDF.
- The PDF is stored inside the configured sandbox workspace.
- The requested output fits within the bounded text/page limits.

## When not to use
- Do not use for remote URL PDFs; use `fetch(operation="pdf")`.
- Do not use for table/image extraction; those operations are not registered.
- Do not use for images or CSV files; use `image` or `sheet`.

## How to call
Call `pdf(operation="text", path="uploads/report.pdf")`. The parser is limited to 500 pages and 100,000 extracted characters.

## Examples
1. Extract local PDF text: `pdf(operation="text", path="uploads/report.pdf")`.
2. Use the returned `pageCount` to describe document length.
3. For an empty text layer, report the empty extraction; do not invent OCR content.
4. For a PDF URL, use `fetch(operation="pdf", url="https://...")`.
5. Wrong operation returns `INVALID_OPERATION`; select `text`.
6. For CSV files, use `sheet(operation="read")`.

## Edge cases
- **Missing file:** report `NOT_FOUND`.
- **Unknown operation:** report `INVALID_OPERATION`.
- **Corrupt PDF:** report `INVALID_PDF`.
- **Page or text limit:** report the explicit limit error rather than partial success.
- **Missing pypdf:** report `DEPENDENCY_MISSING`.
- **Scanned-only document:** text extraction may be empty; do not claim OCR was run.
