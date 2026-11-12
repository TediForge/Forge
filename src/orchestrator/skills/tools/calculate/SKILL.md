---
name: calculate
description: Compute arithmetic expressions precisely when a numeric result matters; do not use for code execution or general symbolic reasoning.
category: tool
version: 1.0
---

# Calculate

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `evaluate` | Evaluate a bounded arithmetic expression | `expression` | implemented |

## When to use
- The user needs exact arithmetic, a conversion, or a numerical result with several operations.
- The result should be evaluated without rounding or mental estimation.
- A value must be checked before being used in a calculation.

## When not to use
- Do not use for general explanation, code, dates, or arbitrary Python.
- Simple mental arithmetic that does not need exact verification may be answered directly.
- Do not use for current time or timezone conversion; use `clock`.
- Do not use for arbitrary code execution or symbolic algebra.

## How to call
`calculate(operation="evaluate", expression: string)` accepts arithmetic operators and the documented math functions only. Use one expression, with no variables or assignments.

## Output and edge cases
Expressions are limited to 1000 characters and exponent magnitude 1000. Use the structured result; on a rejected expression, correct it rather than changing the task to executable code.

## Examples
1. **Arithmetic:** Compute `144 / 12 + 3` with `operation="evaluate"` when exact arithmetic is requested.
2. **Conversion:** Convert a value using an explicit arithmetic expression and unit multiplier.
3. **Parentheses:** Calculate `(18 + 7) * 4` without mental rounding.
4. **Unsupported code:** Do not call with `open(...)`, assignments, imports, or variables.
5. **Adjacent-tool boundary:** For current time, use `clock`; a date is not an arithmetic expression.
6. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`; use `evaluate`.

## Edge cases
- **Division by zero:** report the evaluation error; do not substitute a value.
- **Unsafe syntax:** report `INVALID_EXPRESSION`; never retry as executable code.
- **Oversized expression:** report the length limit and request a smaller expression.
- **Large exponent:** report the bound failure rather than approximate silently.
- **Non-finite result:** surface the evaluation error; do not return infinity or NaN as a valid number.
- **Unsupported operation:** report `INVALID_OPERATION`; do not omit the required operation.
