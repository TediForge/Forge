# Thought IDs

Thought IDs identify user-visible reasoning or progress intent only. They are
stable `T` plus five uppercase alphanumeric values, assigned beside the
emission site and never generated per run. Tool/integration/data identifiers
belong in [action-ids.md](action-ids.md).

| ID | Meaning | Lifecycle |
| --- | --- | --- |
| `T4P8M2` | General reasoning or progress | Active |
| `T9N3Q7` | Analysis and execution-step progress | Active |
| `T6D2V9` | Planning an execution path | Active |
| `T0A1B2` | Synthesis or media preparation | Active |

Former tool Thought IDs are emitted only as deprecated compatibility events
for one release. Those events set `data.deprecated` to `true`; they are not
part of this reasoning-only catalog.
