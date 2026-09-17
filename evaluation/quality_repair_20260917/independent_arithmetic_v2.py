"""Independent audit arithmetic: standard library only, no production imports.

Membership in supplied numeric values and exact calculation are provenance
checks. They do not establish whether the model chose the right mathematical
operation for the user's meaning; strict answer review remains necessary.
"""
import ast
from fractions import Fraction
from functools import lru_cache
import operator
import re

SMALL = dict(zip("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)))
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
VOCABULARY = "|".join([*SMALL, *TENS, "hundred", "thousand", "million", "billion", "trillion"])
NUMBER_PHRASE = re.compile(r"\b(?:" + VOCABULARY + r")(?:[ -]+(?:and[ -]+)?(?:" + VOCABULARY + r"))*\b", re.I)
DIGITS = re.compile(r"(?<![\w.,])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?!\w)(?![.,]\d)")
OPERATIONS = {ast.Add: operator.add, ast.Sub: operator.sub,
              ast.Mult: operator.mul, ast.Div: operator.truediv}


def _small_cardinal(tokens):
    if len(tokens) == 1:
        return SMALL.get(tokens[0], TENS.get(tokens[0]))
    if len(tokens) == 2 and tokens[0] in TENS and 0 < SMALL.get(tokens[1], 0) < 10:
        return TENS[tokens[0]] + SMALL[tokens[1]]
    return None


def _three_digit_cardinal(tokens):
    if len(tokens) > 1 and 0 < SMALL.get(tokens[0], 0) < 10 and tokens[1] == "hundred":
        base = SMALL[tokens[0]] * 100
        remainder = tokens[2:]
        if not remainder:
            return base
        if remainder[0] == "and":
            remainder = remainder[1:]
        value = _small_cardinal(remainder)
        return base + value if value is not None and 0 < value < 100 else None
    return _small_cardinal(tokens)


def _cardinal(tokens):
    if tokens == ["one", "million"]:
        return 1_000_000
    if "thousand" not in tokens:
        return _three_digit_cardinal(tokens)
    if tokens.count("thousand") != 1:
        return None
    split = tokens.index("thousand")
    multiplier = _three_digit_cardinal(tokens[:split])
    tail = tokens[split + 1:]
    if tail[:1] == ["and"]:
        tail = tail[1:]
    remainder = _three_digit_cardinal(tail) if tail else 0
    if multiplier is None or not 1 <= multiplier <= 999 or remainder is None:
        return None
    return multiplier * 1000 + remainder


def _phrase_values(phrase):
    if len(phrase.split()) > 32:
        return ()
    @lru_cache(None)
    def parse(part):
        value = _cardinal(re.split(r"[ -]+", part.lower()))
        if value is not None:
            return (value,)
        boundaries = list(re.finditer(r"\s+and\s+", part, re.I))
        for boundary in reversed(boundaries):
            left, right = parse(part[:boundary.start()]), parse(part[boundary.end():])
            if left and right:
                return left + right
        return ()
    return parse(phrase)


def supplied_magnitudes(request):
    if not isinstance(request, str) or not request or len(request) > 4096:
        return frozenset()
    values = set()
    for match in DIGITS.finditer(request):
        digits = match.group().replace(",", "").lstrip("+-")
        if len(digits) <= 7 and int(digits) <= 1_000_000:
            values.add(int(digits))
    for match in NUMBER_PHRASE.finditer(request):
        values.update(value for value in _phrase_values(match.group()) if 0 <= value <= 1_000_000)
    return frozenset(values)


def arithmetic_directive(request):
    if len(supplied_magnitudes(request)) < 2:
        return False
    unquoted = re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', " ", request)
    if re.search(r"\b(?:convert|conversion)\b", unquoted, re.I):
        return False
    return bool(re.search(r"\b(?:how\s+many|altogether|total|calculate|compute|what\s+is|sum|product|difference|left|remains?|remaining|add|subtract|multiply|divide)\b", unquoted, re.I))


def compute_expression(expression, request):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 160 or not re.fullmatch(r"[0-9+*/() -]+", expression):
        raise ValueError("expression must use at most 160 permitted ASCII characters")
    supplied = supplied_magnitudes(request)
    if not supplied:
        raise ValueError("no current supplied integer values")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError("invalid arithmetic syntax") from error
    nodes = list(ast.walk(tree))
    allowed = (ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.UAdd, ast.USub)
    if len(nodes) > 64 or any(not isinstance(node, allowed) for node in nodes):
        raise ValueError("unsupported operation or more than 64 AST nodes")
    if len(supplied) > 1 and not any(isinstance(node, ast.BinOp) for node in nodes):
        raise ValueError("multiple supplied values require an operation")
    def evaluate(node, depth=0):
        if depth > 16:
            raise ValueError("arithmetic AST exceeds depth 16")
        if isinstance(node, ast.Expression):
            result = evaluate(node.body, depth + 1)
        elif isinstance(node, ast.Constant):
            if type(node.value) is not int or not 0 <= node.value <= 1_000_000 or node.value not in supplied:
                raise ValueError("expression contains an integer absent from the current request")
            result = Fraction(node.value)
        elif isinstance(node, ast.UnaryOp):
            value = evaluate(node.operand, depth + 1)
            result = -value if isinstance(node.op, ast.USub) else value
        elif isinstance(node, ast.BinOp):
            left, right = evaluate(node.left, depth + 1), evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Div) and not right:
                raise ValueError("division by zero")
            result = OPERATIONS[type(node.op)](left, right)
        else:
            raise ValueError("unsupported AST node")
        if abs(result.numerator) > 1_000_000_000_000 or result.denominator > 1_000_000_000_000:
            raise ValueError("intermediate fraction exceeds bounds")
        return result
    result = evaluate(tree)
    if result.denominator != 1 or abs(result.numerator) > 1_000_000_000:
        raise ValueError("result must be an integer with magnitude at most one billion")
    return str(result.numerator)
