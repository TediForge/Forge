---
name: summarize
description: Use to create a bounded extractive summary of supplied text or allowlisted HTTPS pages; do not use when paraphrase or synthesis is required.
category: tool
version: 1.0
---

# Summarize

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `text` | Select salient sentences from supplied text | `text` | implemented |
| `url` | Summarize readable text from an allowlisted HTTPS page | `url` | implemented |

## Overview
`summarize` selects salient source sentences using local word-frequency scoring. It preserves original wording and order; it does not generate a paraphrase or add facts.

## When to use
- The user wants a compact extractive digest of a long passage.
- A short summary must retain source wording for traceability.
- The user asks for an extractive summary of an allowlisted public page.

## When not to use
- Do not use for nuanced synthesis, interpretation, translation, or fact checking.
- Do not use when important meaning depends on structure such as tables or code.
- If a paraphrased or audience-specific summary is needed, summarize directly from the source with the configured language model.
- Do not use for URL discovery; use `search`.
- Do not use a URL outside the configured host allowlist.

## Procedure and call
Call `summarize(operation="text", text, maxSentences=3)` or `summarize(operation="url", url, maxSentences=3)`. URL access is HTTPS-only, host-allowlisted, and bounded to 2 MB.

## Output
Success returns `{success, summary, sentenceCount, method: "extractive", error: null, errorCode: null}`. The summary consists of selected complete sentences from the input.

## Guidelines
- Do not describe the extractive result as a paraphrase.
- Check that selected sentences answer the user's request; provide context if selection misses an important qualification.
- Never infer facts absent from the source.

## Examples
1. **Long report:** Request three key sentences from a supplied report; return up to three salient original sentences.
2. **Short passage:** Request a summary of two sentences with a three-sentence cap; return both unchanged.
3. **Single-sentence cap:** Set `maxSentences` to 1 for a one-sentence extract.
4. **Empty input:** Ask for source text or report the explicit `INVALID_TEXT` result.
5. **Adjacent-tool boundary:** If the user asks for an explanation in simpler words, use language generation rather than this extractive selector.
6. **URL:** `summarize(operation="url", url="https://docs.example.org/guide")` summarizes readable page text.
7. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`.
8. **Fetch boundary:** For the full page content, use `fetch(operation="url")`.

## Edge cases
- **Empty or whitespace-only text:** report `INVALID_TEXT`.
- **Too many characters:** report `TEXT_TOO_LARGE`; do not silently truncate.
- **Invalid sentence limit:** report `INVALID_LIMIT` and request a value from 1 to 10.
- **No sentence punctuation:** return the available text as one sentence rather than inventing boundaries.
- **Tied sentence scores:** the earlier source sentence wins; preserve source order.
- **URL host not allowlisted:** report `HOST_NOT_ALLOWED`; do not claim a fetch.
- **Non-text response:** report `UNSUPPORTED_CONTENT_TYPE`.
- **Empty or oversized page:** report the corresponding typed error; do not summarize partial content.
