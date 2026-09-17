"""Typed layout for general answers; rendering adds only separators and bullets.

Structure is not a correctness judgment. Callers retain original model JSON and
run ordinary evidence, task-contract and answer-review checks after rendering.
"""

from dataclasses import dataclass
import json
import re

from .response import RobotResponse, ResponseValidationError
from .task_contract import csv_output_requested, requested_count, task_instruction


@dataclass(frozen=True)
class TaskLayout:
    kind: str
    count: int | None = None


def task_layout(request):
    if csv_output_requested(request):
        return TaskLayout("csv")
    for unit, kind in ((r"bullet(?:\s+point)?", "bullets"), ("line", "lines"),
                       ("item", "items"), ("sentence", "sentences")):
        count = requested_count(request, unit)
        if count is not None and 1 <= count <= 12:
            return TaskLayout(kind, count)
    return None


def parts_schema(layout):
    minimum, maximum = ((2, 32) if layout.kind == "csv" else (layout.count, layout.count))
    return {"type": "object", "properties": {
        "answer_parts": {"type": "array", "minItems": minimum, "maxItems": maximum,
                         "items": {"type": "string", "minLength": 1, "maxLength": 600}}},
        "required": ["answer_parts"], "additionalProperties": False}


def parts_instruction(request, layout):
    detail = {
        "csv": "Each part is one CSV row. Start with the requested header, then preserve all input rows and values in order. Use commas between cells.",
        "lines": "Each part is one requested line of the answer. Supply the actual content, without a title or introduction unless requested.",
        "bullets": "Each part contains one complete bullet's content. Do not add bullet markers or numbering; the application adds them.",
        "items": "Each part contains one actual requested list item, not a heading or an offer to make a list. Omit numbering.",
        "sentences": "Each part is exactly one complete sentence. Keep any greeting within a sentence, without adding a separate greeting sentence.",
    }[layout.kind]
    count = "" if layout.count is None else f" Produce exactly {layout.count} parts."
    return (
        "Complete the user's task. Return only JSON with answer_parts, an array of strings. "
        + detail + count +
        " No line breaks inside a part, code fences, or JSON field names in the answer text. "
        "Include every requested detail and constraint; do not merely announce the answer. "
        "Use at most 80 words overall. Use current supplied information and general knowledge. "
        "Do not invent personal facts or claim the robot performed an action. "
        "A requested draft is wording for the human, not a claim about the robot. "
        + task_instruction(request)
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
    if layout.kind == "csv" and len(parts) < 2:
        raise ResponseValidationError("CSV requires a header and data")
    for part in parts:
        if type(part) is not str or not part.strip() or len(part) > 600 or "\n" in part:
            raise ResponseValidationError("each task part must be one nonempty line")
        if layout.kind in {"items", "bullets"} and re.match(r"\s*(?:[-*•]|\d+[.)])\s", part):
            raise ResponseValidationError("task items must omit application list markers")
    separator = " " if layout.kind == "sentences" else "\n"
    marker = "- " if layout.kind in {"items", "bullets"} else ""
    speech = separator.join(marker + part.strip() for part in parts)
    # RobotResponse enforces controls, machine-field/selector exclusion and the
    # exact public response contract, including NO_ACTION and no memory IDs.
    return RobotResponse(speech=speech, gesture_id="NO_ACTION", memory_used=())
