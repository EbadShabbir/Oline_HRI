"""Typed general answers with source-bound formatting and exact arithmetic.

Formatting and expression evaluation do not establish task correctness.
Callers retain original model JSON and
run ordinary evidence, task-contract and answer-review checks after rendering.
"""

from dataclasses import dataclass
import json
import re

from .response import RobotResponse, ResponseValidationError
from .arithmetic import arithmetic_request, evaluate_integer_expression, expression_instruction
from .task_contract import (csv_output_requested, requested_count, task_instruction,
                            requested_csv_header, scalar_output_requested,
                            numbered_output_requested, requested_line_prefixes)


@dataclass(frozen=True)
class TaskLayout:
    kind: str
    count: int | None = None
    numbered: bool = False
    prefixes: tuple[str, ...] = ()
    header: str | None = None
    source_request: str | None = None


def task_layout(request):
    if csv_output_requested(request):
        return TaskLayout("csv", header=requested_csv_header(request))
    if scalar_output_requested(request):
        if arithmetic_request(request):
            return TaskLayout("calculation", 1, source_request=request)
        return TaskLayout("integer", 1)
    for unit, kind in ((r"bullet(?:\s+point)?", "bullets"), ("line", "lines"),
                       ("item", "items"), ("step", "items"), ("sentence", "sentences")):
        count = requested_count(request, unit)
        if count is not None and 1 <= count <= 12:
            return TaskLayout(kind, count, numbered_output_requested(request),
                              requested_line_prefixes(request, count))
    if re.search(r"\b(?:separate\s+lines|each\s+on\s+(?:its\s+own|a\s+separate)\s+line)\b", request, re.I):
        count = requested_count(request, "name")
        if count is not None and 1 <= count <= 12:
            return TaskLayout("lines", count)
    return None


def parts_schema(layout):
    minimum, maximum = (((1 if layout.header else 2), 32) if layout.kind == "csv" else (layout.count, layout.count))
    item = {"type": "string", "minLength": 1, "maxLength": 600}
    if layout.kind == "integer":
        item["pattern"] = r"^[+-]?\d+$"
    if layout.kind == "calculation":
        item["pattern"] = r"^[0-9+*/() -]+$"
        item["maxLength"] = 160
    return {"type": "object", "properties": {
        "answer_parts": {"type": "array", "minItems": minimum, "maxItems": maximum,
                         "items": item}},
        "required": ["answer_parts"], "additionalProperties": False}


def parts_instruction(request, layout):
    if layout.kind == "calculation":
        return ("Return only JSON with answer_parts, an array containing one short arithmetic expression string. "
                + expression_instruction(request)
                + " The application evaluates the expression and delivers only the integer. "
                "Do not put the calculated answer, an equals sign, prose or units inside the array.")
    detail = {
        "csv": "Each part is one CSV row. Start with the requested header, then preserve all input rows and values in order. Use commas between cells.",
        "lines": "Each part is one requested line of the answer. Supply the actual content, without a title or introduction unless requested.",
        "bullets": "Each part contains one complete bullet's content. Do not add bullet markers or numbering; the application adds them.",
        "items": "Each part contains one actual requested list item, not a heading or an offer to make a list. Omit numbering.",
        "sentences": "Each part is exactly one complete sentence. Keep any greeting within a sentence, without adding a separate greeting sentence.",
        "integer": "The single part contains only the computed integer in digits. No equation, label, units or explanation.",
    }[layout.kind]
    if layout.header:
        detail = f"Each part is one CSV DATA row, preserving every supplied row and value in order. The application prepends the exact header {layout.header!r}."
    if layout.numbered:
        detail += " Omit numbering: the application numbers the parts consecutively."
    if layout.prefixes:
        detail += f" The application prefixes the parts in order with {layout.prefixes!r}; omit those labels from your content."
    count = "" if layout.count is None else f" Produce exactly {layout.count} parts."
    return (
        "Complete the user's task. Return only JSON with answer_parts, an array of strings. "
        + detail + count +
        " No line breaks inside a part, code fences, or JSON field names in the answer text. "
        "Include every requested detail and constraint; preserve supplied objects, quantities, materials, times and locations. Do not merely announce the answer. "
        "For an explanation, name the physical cause and connect it to the observed result without contradicting it. "
        "Use at most 80 words overall. Use current supplied information and general knowledge. "
        "Do not invent personal facts or claim the robot performed an action. "
        "A requested draft is wording for the human, not a claim about the robot. "
        + task_instruction(request)
        + (" Numbering and the specified prefixes are rendered by the application: omit them inside answer_parts."
           if layout.numbered or layout.prefixes else "")
    )


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResponseValidationError("task parts contain duplicate fields")
        result[key] = value
    return result


def _constant(value):
    raise ResponseValidationError("task parts contain nonstandard JSON")


def parse_parts(content, layout):
    if not isinstance(content, str) or len(content) > 8192:
        raise ResponseValidationError("task parts must be bounded JSON")
    try:
        data = json.loads(content, object_pairs_hook=_unique, parse_constant=_constant)
    except (ValueError, TypeError, RecursionError) as error:
        raise ResponseValidationError("task parts are not valid JSON") from error
    if type(data) is not dict or set(data) != {"answer_parts"}:
        raise ResponseValidationError("task parts require exactly answer_parts")
    parts = data["answer_parts"]
    if type(parts) is not list or not 1 <= len(parts) <= 32:
        raise ResponseValidationError("task parts require a bounded nonempty list")
    if layout.count is not None and len(parts) != layout.count:
        raise ResponseValidationError("task parts have the wrong count")
    if layout.kind == "csv" and not layout.header and len(parts) < 2:
        raise ResponseValidationError("CSV requires a header and data")
    normalized = []
    for index, part in enumerate(parts, 1):
        if type(part) is not str or not part.strip() or len(part) > 600 or "\n" in part:
            raise ResponseValidationError("each task part must be one nonempty line")
        if layout.numbered:
            # Matching consecutive list markers are structure, not content.
            # A different numeral remains invalid rather than silently changed.
            part = re.sub(r"^\s*" + str(index) + r"[.)]\s+", "", part)
        if (layout.kind in {"items", "bullets"} or layout.numbered) and re.match(r"\s*(?:[-*•]|\d+[.)])\s", part):
            raise ResponseValidationError("task items must omit application list markers")
        if not part.strip():
            raise ResponseValidationError("task part requires content after its marker")
        normalized.append(part.strip())
    if layout.kind == "integer" and not re.fullmatch(r"[+-]?\d+", parts[0].strip()):
        raise ResponseValidationError("scalar answer must contain only an integer")
    parts = normalized
    if layout.kind == "calculation":
        parts = [evaluate_integer_expression(parts[0], layout.source_request)]
    if layout.prefixes:
        parts = [prefix + " " + (part[len(prefix):].lstrip() if part.startswith(prefix) else part)
                 for prefix, part in zip(layout.prefixes, parts)]
    if layout.header:
        parts.insert(0, layout.header)
    separator = " " if layout.kind == "sentences" else "\n"
    marker = "- " if layout.kind in {"items", "bullets"} else ""
    speech = separator.join((f"{index}. " if layout.numbered else marker) + part
                            for index, part in enumerate(parts, 1))
    # RobotResponse enforces controls, machine-field/selector exclusion and the
    # exact public response contract, including NO_ACTION and no memory IDs.
    return RobotResponse(speech=speech, gesture_id="NO_ACTION", memory_used=())
