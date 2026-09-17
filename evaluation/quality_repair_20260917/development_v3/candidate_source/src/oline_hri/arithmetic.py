"""Bounded exact arithmetic using integer operands in the current request.

The model supplies an expression; the application computes its integer result.
Only +, -, *, /, parentheses and unary signs are accepted. Operand membership
does not prove that the expression represents the user's intended calculation;
ordinary task and answer review must still check that meaning. This module has
no access to history, memory, names, functions or Python evaluation.
"""

from __future__ import annotations

import ast
from fractions import Fraction
import re

from .response import ResponseValidationError


MAX_EXPRESSION_CHARACTERS = 160
MAX_REQUEST_CHARACTERS = 4096
MAX_AST_NODES = 64
MAX_AST_DEPTH = 16
MAX_OPERAND = 1_000_000
MAX_FRACTION_COMPONENT = 1_000_000_000_000
MAX_INTEGER_RESULT = 1_000_000_000

_SMALL = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(),
    range(20),
))
_TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
_NUMBER_WORD = "(?:" + "|".join((*_SMALL, *_TENS, "hundred", "thousand", "million", "billion", "trillion")) + ")"
_WORD_NUMBER = re.compile(r"\b" + _NUMBER_WORD + r"(?:[ -]+(?:and[ -]+)?" + _NUMBER_WORD + r")*\b", re.I)
_DIGIT_NUMBER = re.compile(r"(?<![\w.,])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?!\w)(?![.,]\d)")
_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                  ast.Add, ast.Sub, ast.Mult, ast.Div, ast.UAdd, ast.USub)


def _under_hundred(words: list[str]) -> int | None:
    if len(words) == 1:
        return _SMALL.get(words[0], _TENS.get(words[0]))
    if len(words) == 2 and words[0] in _TENS and 1 <= _SMALL.get(words[1], 0) <= 9:
        return _TENS[words[0]] + _SMALL[words[1]]
    return None


def _under_thousand(words: list[str]) -> int | None:
    if len(words) >= 2 and 1 <= _SMALL.get(words[0], 0) <= 9 and words[1] == "hundred":
        rest = words[2:]
        if not rest:
            return _SMALL[words[0]] * 100
        if rest[:1] == ["and"]:
            rest = rest[1:]
        remainder = _under_hundred(rest)
        if remainder is not None and 1 <= remainder <= 99:
            return _SMALL[words[0]] * 100 + remainder
        return None
    return _under_hundred(words)


def _word_value(text: str) -> int | None:
    words = re.split(r"[ -]+", text.casefold())
    if words == ["one", "million"]:
        return MAX_OPERAND
    if "thousand" not in words:
        return _under_thousand(words)
    if words.count("thousand") != 1:
        return None
    offset = words.index("thousand")
    thousands = _under_thousand(words[:offset])
    rest = words[offset + 1:]
    if rest[:1] == ["and"]:
        rest = rest[1:]
    remainder = _under_thousand(rest) if rest else 0
    if thousands is not None and 1 <= thousands <= 999 and remainder is not None:
        return thousands * 1000 + remainder
    return None


def _word_values(text: str) -> tuple[int, ...]:
    # "one hundred and three" is one operand, while "one and three" is two.
    # Split conjunctions only when the whole phrase is not a cardinal number.
    if len(text.split()) > 32:
        return ()
    cache = {}

    def split(phrase: str) -> tuple[int, ...]:
        if phrase in cache:
            return cache[phrase]
        value = _word_value(phrase)
        if value is not None:
            cache[phrase] = (value,)
            return (value,)
        for match in reversed(tuple(re.finditer(r"\s+and\s+", phrase, re.I))):
            left, right = split(phrase[:match.start()]), split(phrase[match.end():])
            if left and right:
                cache[phrase] = left + right
                return left + right
        cache[phrase] = ()
        return ()

    return split(text)


def supplied_integer_operands(request: str) -> frozenset[int]:
    """Return bounded integer magnitudes written in this request only.

    Recognized forms are digits, correctly grouped comma digits, and bounded
    English cardinal numbers. Decimal and scientific notation are not split
    into misleading integer operands. Signs remain expression operators; the
    membership check alone cannot establish their intended meaning.
    """
    if not isinstance(request, str) or not request or len(request) > MAX_REQUEST_CHARACTERS:
        return frozenset()
    values = set()
    for match in _DIGIT_NUMBER.finditer(request):
        # Avoid converting unbounded digit strings even inside a short request.
        token = match.group().replace(",", "").lstrip("+-")
        if len(token) <= 7:
            value = int(token)
            if value <= MAX_OPERAND:
                values.add(value)
    for match in _WORD_NUMBER.finditer(request):
        values.update(value for value in _word_values(match.group()) if 0 <= value <= MAX_OPERAND)
    return frozenset(values)


def arithmetic_request(request: str) -> bool:
    """Select explicit arithmetic with supplied quantities, excluding conversion.

    This is only a format-selection hint. Existing dependency/evidence routing
    still decides whether the current request can use general generation.
    """
    operands = supplied_integer_operands(request)
    if len(operands) < 2:
        return False
    directive = re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', " ", request)
    if re.search(r"\b(?:convert|conversion)\b", directive, re.I):
        return False
    return bool(re.search(
        r"\b(?:how\s+many|altogether|total|calculate|compute|what\s+is|sum|product|"
        r"difference|left|remains?|remaining|add|subtract|multiply|divide)\b", directive, re.I))


def expression_instruction(request: str) -> str:
    """Guidance for a single expression part; no result or recalled fact is supplied."""
    operands = ", ".join(str(value) for value in sorted(supplied_integer_operands(request)))
    return (
        "Write one arithmetic expression that represents the requested calculation, not a guessed result. "
        "Use only integer operands supplied in the current request, +, -, *, / and parentheses. "
        "Translate supplied number words into digits. Preserve their roles, grouping and signs; "
        "use each quantity where the task calls for it, including quantities applied only once. "
        "Do not introduce constants, names, functions, powers, units, equations or explanation. "
        "The application computes the exact expression and renders only its integer result. "
        f"Available integer operand magnitudes: {operands or 'none; an expression cannot be grounded'}."
    )


def evaluate_integer_expression(expression: str, request: str) -> str:
    """Compute a bounded expression or reject it with ResponseValidationError."""
    if (not isinstance(expression, str) or not expression.strip()
            or len(expression) > MAX_EXPRESSION_CHARACTERS
            or not re.fullmatch(r"[0-9+*/() -]+", expression)):
        raise ResponseValidationError("arithmetic requires a bounded expression using integer operands")
    operands = supplied_integer_operands(request)
    if not operands:
        raise ResponseValidationError("arithmetic has no supplied integer operands")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ResponseValidationError("arithmetic expression is invalid") from error
    nodes = tuple(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES or any(not isinstance(node, _ALLOWED_NODES) for node in nodes):
        raise ResponseValidationError("arithmetic expression contains unsupported syntax or too many operations")
    if len(operands) > 1 and not any(isinstance(node, ast.BinOp) for node in nodes):
        raise ResponseValidationError("multiple supplied quantities require a calculation, not a result guess")

    def visit(node: ast.AST, depth: int = 0) -> Fraction:
        if depth > MAX_AST_DEPTH:
            raise ResponseValidationError("arithmetic expression is nested too deeply")
        if isinstance(node, ast.Expression):
            value = visit(node.body, depth + 1)
        elif isinstance(node, ast.Constant):
            if type(node.value) is not int or not 0 <= node.value <= MAX_OPERAND or node.value not in operands:
                raise ResponseValidationError("arithmetic operand was not supplied in the current request")
            value = Fraction(node.value)
        elif isinstance(node, ast.UnaryOp):
            operand = visit(node.operand, depth + 1)
            value = -operand if isinstance(node.op, ast.USub) else operand
        elif isinstance(node, ast.BinOp):
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            else:
                if not right:
                    raise ResponseValidationError("arithmetic cannot divide by zero")
                value = left / right
        else:
            raise ResponseValidationError("arithmetic expression contains unsupported syntax")
        if abs(value.numerator) > MAX_FRACTION_COMPONENT or value.denominator > MAX_FRACTION_COMPONENT:
            raise ResponseValidationError("arithmetic intermediate value exceeds its magnitude limit")
        return value

    try:
        result = visit(tree)
    except (OverflowError, RecursionError, ZeroDivisionError) as error:
        raise ResponseValidationError("arithmetic calculation exceeded its bounds") from error
    if result.denominator != 1:
        raise ResponseValidationError("arithmetic result must be an exact integer")
    if abs(result.numerator) > MAX_INTEGER_RESULT:
        raise ResponseValidationError("arithmetic integer result exceeds its magnitude limit")
    return str(result.numerator)
