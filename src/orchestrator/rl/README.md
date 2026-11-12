# Offline post-training boundary

## Ownership

This package is reserved for offline post-training: preference data, reward
models, policy optimization, and offline evaluation. It does not own online
inference, request routing, tool execution, or API lifecycle.

## Outputs

Future training workers may export versioned policy artifacts (weights or
adapters). Inference may load those artifacts through a configured inference
source and backend. This is a one-way artifact handoff, not a shared training
loop.

## Non-goals and allowed interaction

Training workers must not import or call `orchestrator.api` or
`orchestrator.engine`. They may write artifacts to a source that inference
already understands. Serving packages must never import `orchestrator.rl`.

The opt-in trajectory JSONL export is a data handoff for evaluation and future
preference curation; it does not train a model automatically.

`fixtures/preferences.jsonl` is a small example preference pair used to verify
that offline evaluation data can be loaded. It is not production or user data.
