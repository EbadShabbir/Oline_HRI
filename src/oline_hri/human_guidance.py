"""Bounded human-instruction format for a practical-help quality retry.

This format supplies neither personal evidence nor a semantic correctness
guarantee. Callers still run the ordinary evidence and quality checks on the
rendered response, and retain the model's original JSON separately.
"""

import json
import re
import unicodedata

from .reply_guard import has_unstated_recall_intent, is_drafting_followup, is_drafting_request
from .response import NO_ACTION, ResponseValidationError, RobotResponse


_MAX_CONTENT = 8192
_MAX_STEP = 240
_MAX_WORDS = 80
_SMALL_NUMBERS = {
    word: index for index, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60}
_UNITS = r"(?:one|two|three|four|five|six|seven|eight|nine)"
_NUMBER = (r"(?:\d+|(?:twenty|thirty|forty|fifty)(?:[ -]" + _UNITS + r")?|sixty|"
           + "|".join(_SMALL_NUMBERS) + r")")
_BUDGET = re.compile(
    r"\b(?:(?:i|we)\s+(?:only\s+)?have\s+(?:only\s+)?|in\s+|within\s+)"
    r"(?P<plain>" + _NUMBER + r")\s+minutes?\b|"
    r"(?<![\w.+-])(?P<adjective>" + _NUMBER + r")[ -]minute[ -]"
    r"(?:plan|checklist|routine|session)\b", re.I,
)
_LIST_MARKER = re.compile(
    r"^\s*(?:(?:(?:step\s+)?\(?\d+[.):]|[a-z][.)]|[ivxlcdm]+[.)])(?:\s|$)|"
    r"[-*+](?:\s|$)|[•‣▪–—])", re.I,
)
# Eligibility is deliberately narrower than general advice. These are action
# verbs, not a catalog of tasks or a whitelist of permissible answers.
_ACTION = (r"(?:tidy|organize|organise|clean|sort|pack|unpack|fold|prepare|plan|schedule|"
           r"repair|fix|troubleshoot|install|configure|set\s+up|build|"
           r"practice|practise|assemble|arrange|start)")
_HELP = re.compile(
    r"^(?:(?:please\s+)?(?:can|could|would)\s+you\s+)?(?:please\s+)?"
    r"help\s+me\s+(?:to\s+)?" + _ACTION + r"\s+\S", re.I,
)
_HOW_TO = re.compile(
    r"^how\s+(?:(?:can|could|should|do)\s+i\s+|to\s+)" + _ACTION + r"\s+\S", re.I,
)
_PLAN = re.compile(
    r"^(?:please\s+)?(?:plan\s+\S|"
    r"(?:give|create|make|outline)\s+(?:me\s+)?(?:a\s+)?"
    r"(?:(?:short|simple|practical|step-by-step)\s+|" + _NUMBER + r"[ -]minute[ -])?"
    r"(?:plan|checklist|steps)\s+(?:for|to)\s+\S)", re.I,
)
_OTHER_REQUEST = re.compile(
    r"^(?:(?:please|can\s+you|could\s+you|would\s+you)\s+)*"
    r"(?:explain|define|describe|compare|distinguish|differentiate|"
    r"translate|write|draft|compose|rewrite|ask|clarify)\b|"
    r"\b(?:capabilities|abilities|limitations)\b", re.I,
)
_FIRST_PERSON = re.compile(r"\b(?:i|we|me|my|mine|us|our|ours)\b|\blet['’]s\b", re.I)
_ROBOT_ACTOR = re.compile(
    r"\b(?:the\s+)?(?:assistant|robot)\s+(?:can|could|will|would|shall|"
    r"must|should|is|has|does)\b", re.I,
)


def guidance_requested(request: str) -> bool:
    """Recognize explicit practical instructions, not a bare request for help."""
    if not isinstance(request, str) or not request.strip():
        return False
    text = unicodedata.normalize("NFKC", request).strip()
    if (is_drafting_request(text) or is_drafting_followup(text)
            or has_unstated_recall_intent(text)):
        return False
    clauses = tuple(part.strip() for part in re.split(r"(?<=[.!?])\s+|[;\n]", text))
    if any(_OTHER_REQUEST.search(clause) for clause in clauses):
        return False
    return any(_HELP.search(clause) or _HOW_TO.search(clause) or _PLAN.search(clause)
               for clause in clauses)


def guidance_time_budget(request: str) -> int | None:
    """Read one explicit whole-minute budget; ambiguous units stay untimed.

    Written numbers cover one through sixty; digits cover one through 120.
    This is a bounded duration grammar, not a general temporal interpreter.
    """
    if not isinstance(request, str):
        return None
    text = unicodedata.normalize("NFKC", request).casefold()
    if len(re.findall(r"\bminutes?\b", text)) != 1:
        return None
    if re.search(r"\b(?:seconds?|hours?|days?|weeks?)\b", text):
        return None
    matches = tuple(_BUDGET.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    # A duration range/estimate is not an exact allocation budget. In the
    # adjective form the qualifier can sit before the matched number.
    if re.search(r"\b(?:about|around|roughly|approximately|between|up\s+to|"
                 r"at\s+(?:most|least)|more\s+than|less\s+than|minus|negative|to|or|and)\s+(?:a\s+)?$",
                 text[:match.start()]):
        return None
    if (match.group("adjective") and re.search(
            r"\b(?:" + _NUMBER + r"|hundred|thousand)\s+$", text[:match.start()])):
        return None
    if re.match(r"\s*,?\s*(?:(?:or|to)\s+(?:" + _NUMBER + r"|so)\b|give\s+or\s+take\b)",
                text[match.end():]):
        return None
    words = (match.group("plain") or match.group("adjective")).replace("-", " ").split()
    if len(words) == 1 and words[0].isdigit() and len(words[0]) > 3:
        return None
    if len(words) == 1:
        value = int(words[0]) if words[0].isdigit() else _SMALL_NUMBERS.get(words[0], _TENS.get(words[0]))
    else:
        value = _TENS[words[0]] + _SMALL_NUMBERS[words[1]]
    return value if value is not None and 1 <= value <= 120 else None


def _checked_minutes(minutes):
    if minutes is not None and (type(minutes) is not int or not 1 <= minutes <= 120):
        raise ResponseValidationError("guidance budget must be one to 120 whole minutes")


def guidance_schema(*, minutes: int | None = None) -> dict:
    """Return a fresh closed schema; numbering and timer framing are app-owned."""
    _checked_minutes(minutes)
    return {
        "type": "object",
        "properties": {
            "steps_for_user": {
                "type": "array", "minItems": 1, "maxItems": 5,
                "items": {"type": "string", "minLength": 1, "maxLength": _MAX_STEP},
            },
        },
        "required": ["steps_for_user"],
        "additionalProperties": False,
    }


def guidance_instruction(*, minutes: int | None = None) -> str:
    _checked_minutes(minutes)
    timing = ("" if minutes is None else
              f"The available budget is {minutes} minutes. Choose actions that fit it. "
              "The application adds a timer and stop rule; supply no durations or time labels. ")
    word_budget = 75 if minutes is None else 65
    return (
        "Return only JSON with steps_for_user: an array of 1 to 5 short instruction strings. "
        "Give minimal useful steps for the current task, respecting its stated supplies and destination. "
        "Do not require extra equipment or arbitrary measurements. "
        + timing +
        "Address the human in imperative voice; "
        "the human performs every step and the assistant supplies text. "
        "Provide the actions themselves, without offers, introductions or questions. "
        f"Use at most {word_budget} instruction words in total. Leave numbering to the application. "
        "Personal facts require current supplied assertions; task history is not personal evidence."
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResponseValidationError("guidance contains duplicate JSON fields")
        result[key] = value
    return result


def _reject_constant(value):
    raise ResponseValidationError("guidance contains a nonstandard JSON value")


def parse_guidance(content: str, *, minutes: int | None = None) -> RobotResponse:
    """Validate and render instructions without altering the original model JSON.

    A supplied minute budget adds an application-authored timer and stop rule.
    First-person wording is conservatively excluded even inside quoted text;
    this narrow format is not used for drafted artifacts. Instruction meaning
    remains subject to the caller's independent answer review.
    """
    _checked_minutes(minutes)
    if not isinstance(content, str) or len(content) > _MAX_CONTENT:
        raise ResponseValidationError("guidance must be bounded JSON text")
    try:
        value = json.loads(content, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ResponseValidationError("guidance is not valid JSON") from exc
    if type(value) is not dict or set(value) != {"steps_for_user"}:
        raise ResponseValidationError("guidance must contain only steps_for_user")
    steps = value["steps_for_user"]
    if type(steps) is not list or not 1 <= len(steps) <= 5:
        raise ResponseValidationError("guidance requires one to five steps")
    rendered = []
    for index, step in enumerate(steps, 1):
        label = f"{index}. "
        if type(step) is not str or not step.strip() or len(step) > _MAX_STEP:
            raise ResponseValidationError("guidance step must be a short nonempty string")
        normalized = unicodedata.normalize("NFKC", step)
        if _LIST_MARKER.search(normalized):
            raise ResponseValidationError("guidance instructions must omit list markers")
        if _FIRST_PERSON.search(normalized) or _ROBOT_ACTOR.search(normalized):
            raise ResponseValidationError("guidance steps must address the human, not a robot actor")
        if any(unicodedata.category(char).startswith("C") or char in "\u2028\u2029" for char in step):
            raise ResponseValidationError("guidance steps must be plain single-line text")
        rendered.append(label + step.strip())
    speech = " ".join(rendered)
    if minutes is not None:
        speech = f"Set a {minutes}-minute timer. " + speech + " Stop when it rings."
    if len(speech.split()) > _MAX_WORDS:
        raise ResponseValidationError("guidance exceeds eighty speech words")
    return RobotResponse(speech=speech, gesture_id=NO_ACTION, memory_used=())
