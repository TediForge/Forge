# Runtime Sandbox

The sandbox is runtime storage, separate from `src/`. Tool paths are resolved under `workspace/` using `policy.json`.

- `workspace/uploads/` is read-only to tools.
- `workspace/outputs/` stores persistent generated files.
- `workspace/tmp/` stores temporary files and is cleaned at the start of Responses runs when older than the configured retention period.
- Paths must use an allowed extension and remain within an allowed root. Reads are limited by `maxFileSizeMb`.

Set `FORGE_SANDBOX_ROOT` to use a different sandbox root. Update `policy.json` rather than adding per-tool filesystem exceptions.