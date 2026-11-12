---
name: clock
description: Use to get current time or convert an ISO timestamp between IANA zones; do not use for historical facts or date arithmetic.
category: tool
version: 1.0
---

# Clock

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `now` | Retrieve the current date and time | `timezone` (optional) | implemented |
| `convert` | Convert an ISO 8601 timestamp between timezones | `from_timezone`, `to_timezone`, `timestamp` | implemented |

## When to use
- The user asks for the current time/date or an answer depends on the current timestamp.
- The user asks to convert a timestamp between explicit timezones.
- The answer needs a weekday or date boundary in a named zone.

## When not to use
- Do not use for historical dates or arithmetic that does not depend on now.
- Do not use as a substitute for elapsed-time arithmetic; use `calculate`.
- Do not use ambiguous timezone abbreviations when an IANA zone is needed.

## How to call
`clock(operation="now", timezone="UTC")` or `clock(operation="convert", from_timezone, to_timezone, timestamp)`. A timezone-naive timestamp is interpreted in `from_timezone`.

## Output and edge cases
Returns the current ISO timestamp, date, time, weekday, and requested timezone. If a timezone is invalid, report the error and ask for a valid zone; never substitute a guessed local offset.

## Examples
1. **Current UTC time:** Call `clock(operation="now")` to use the UTC default.
2. **Named zone:** Call `clock(operation="now", timezone="Africa/Lagos")` when the user specifies Lagos.
3. **Today:** Use the returned date and weekday for a current-date question.
4. **Historical date:** Answer from reliable context; do not use `clock` to retrieve history.
5. **Adjacent-tool boundary:** For elapsed-time arithmetic, use `calculate` after obtaining the required current timestamp.
6. **Convert timestamp:** `clock(operation="convert", from_timezone="UTC", to_timezone="Africa/Lagos", timestamp="2025-01-15T12:00:00")`.
7. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`; use `now` or `convert`.

## Edge cases
- **Invalid IANA zone:** report `INVALID_TIMEZONE`; ask for a valid zone.
- **No timezone specified:** use the documented UTC default, not the machine's local zone.
- **Day boundary:** use the returned date for that timezone.
- **Historical request:** distinguish current time from historical facts.
- **Timezone abbreviations:** ask for an unambiguous IANA name when an abbreviation is unclear.
- **Invalid conversion timestamp:** report `INVALID_TIMESTAMP` or `INVALID_TIMEZONE`; do not guess an offset.
- **Naive timestamp:** interpret it in the supplied source zone.
- **Offset-aware timestamp:** preserve its instant and convert to the requested target zone.
