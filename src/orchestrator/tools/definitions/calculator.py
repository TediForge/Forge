"""Safe calculator tools."""

import ast
import math
import operator
from typing import Any

from orchestrator.tools.actions import action_handler


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "log": math.log,
    "max": max,
    "min": min,
    "pow": pow,
    "round": round,
    "sqrt": math.sqrt,
}


@action_handler("A4M9Q2", "Evaluating a calculation")
def calculate(operation: str, expression: str) -> dict[str, Any]:
    if operation != "evaluate":
        return {
            "success": False,
            "operation": operation,
            "error": "Unsupported calculate operation",
            "errorCode": "INVALID_OPERATION",
        }
    if not isinstance(expression, str):
        return _failure("", "Expression must be a string", "INVALID_EXPRESSION")
    if len(expression) > 1000:
        return _failure(expression[:1000], "Expression exceeds the 1000 character limit", "LENGTH_EXCEEDED")

    def evaluate(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and not isinstance(node.value, bool) and isinstance(node.value, (int, float)):
            return _validate_result(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("Exponent magnitude exceeds the 1000 limit")
            value = _BINARY_OPERATORS[type(node.op)](left, right)
            return _validate_result(value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
            args = [evaluate(arg) for arg in node.args]
            if node.keywords:
                raise ValueError("Keyword arguments are not supported")
            return _validate_result(_FUNCTIONS[node.func.id](*args))
        raise ValueError("Unsupported syntax in expression")

    try:
        value = evaluate(ast.parse(expression, mode="eval"))
        return {
            "success": True,
            "expression": expression,
            "result": value,
            "error": None,
            "errorCode": None,
        }
    except SyntaxError:
        return _failure(expression, "Expression syntax is invalid", "INVALID_EXPRESSION")
    except (ValueError, ZeroDivisionError, OverflowError, TypeError, RecursionError, MemoryError) as exc:
        message = str(exc) or "Expression could not be evaluated"
        code = "INVALID_EXPRESSION" if message.startswith("Unsupported syntax") else "EVALUATION_ERROR"
        return _failure(expression, message, code)


def _validate_result(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expression did not produce a real number")
    if isinstance(value, int) and value.bit_length() > 4096:
        raise ValueError("Result exceeds the 4096-bit limit")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Result is not finite")
    return value


def _failure(expression: str, message: str, errorCode: str) -> dict[str, Any]:
    return {
        "success": False,
        "expression": expression,
        "result": None,
        "error": message,
        "errorCode": errorCode,
    }


TOOLS = [{
    "type": "function",
    "function": {
        "name": "calculate",
        "description": (
            "Use for arithmetic requiring precise calculation rather than mental math. "
            "Provide one expression string using numbers, +, -, *, /, //, %, **, unary signs, "
            "and the functions abs, ceil, floor, log, max, min, pow, round, sqrt. "
            "Do not use variables, assignments, imports, or other Python syntax. "
            "Expressions are limited to 1000 characters and exponent magnitude to 1000. "
            "Returns a structured result or an error the agent can use to correct the expression."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["evaluate"]},
                "expression": {"type": "string", "maxLength": 1000, "description": "A single arithmetic expression, such as '(12 + 8) * 2'"},
            },
            "required": ["operation", "expression"],
            "additionalProperties": False,
        },
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "expression": {"type": "string"},
            "result": {"type": ["number", "null"]},
            "error": {"type": ["string", "null"]},
            "errorCode": {"type": ["string", "null"]},
        },
        "required": ["success", "expression", "result", "error", "errorCode"],
        "additionalProperties": False,
    },
}]
HANDLERS = {"calculate": calculate}
