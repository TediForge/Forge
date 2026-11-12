---
name: translate
description: Use to translate supplied text or UTF-8 documents with Forge Text; do not use for summarization or unsupported binary files.
category: tool
---

# Translate

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `text` | Translate supplied text | `text`, `target_language` | implemented |
| `document` | Translate a UTF-8 text document | `path`, `target_language` | implemented |

## When to use
- The user explicitly asks to translate text into a target language.
- The user asks to translate a sandboxed UTF-8 text document.
- The configured local Forge Text provider is available.

## When not to use
- Do not use for binary PDFs or images; use an appropriate extraction tool first.
- Do not use summarization as a substitute for translation.
- Do not use when the user has not identified a target language.

## How to call
Call `translate(operation="text", text, target_language)` or `translate(operation="document", path, target_language)`. Inference is performed by the configured local model; no supplied text is sent to a remote translation API.

## Examples
1. Text: `translate(operation="text", text="Good morning.", target_language="French")`.
2. Document: `translate(operation="document", path="uploads/letter.txt", target_language="Spanish")`.
3. Preserve meaning and formatting; inspect the returned translation.
4. If the provider is not configured, report `PROVIDER_NOT_CONFIGURED`.
5. Wrong operation returns `INVALID_OPERATION`; do not call a different operation silently.
6. For summaries, use `summarize` only when summarization is requested.

## Edge cases
- **Provider missing:** report `PROVIDER_NOT_CONFIGURED`; do not fabricate a translation.
- **Unknown operation:** report `INVALID_OPERATION`.
- **Missing language pair:** no translation occurs.
- **Unreadable document:** report `READ_ERROR`; do not claim translation.
- **Oversized text:** report `TEXT_TOO_LARGE`.
- **Empty provider output:** report `INVALID_PROVIDER_RESULT`.
- **Adjacent summarization:** translation and summarization are distinct tasks.
