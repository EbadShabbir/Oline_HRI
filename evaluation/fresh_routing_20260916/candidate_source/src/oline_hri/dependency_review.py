"""One Boolean check of indispensable personal facts, never fact authority.

The local classifier retains the optional/clarify distinction. This review is
fallible: it missed a corrected-time development request even with safe history.
Evidence authorization must remain independent of its returned Boolean.
"""

from copy import deepcopy
import json
import re

from .ollama import ChatMessage
from .reply_guard import _QUESTION_START
from .routing import RoutingError, _object_without_duplicate_keys


REVIEW_VARIANT = "C"
MAX_CANDIDATES = 3
MAX_REVIEW_CHARACTERS = 1024
DEPENDENCY_REVIEW_SCHEMA = {
    "type": "object", "properties": {"needs_personal_facts": {"type": "boolean"}},
    "required": ["needs_personal_facts"], "additionalProperties": False,
}
DEPENDENCY_REVIEW_PROMPT = """Could a stranger fulfill this request using only current_message and the supplied general task context? Return needs_personal_facts=true only when an exact personal value, past decision, location, relationship, or constraint absent from that input is indispensable. Questions are not assertions. Generic discussion does not fulfill a request for the person's actual value. General knowledge, current assertions, and supplied drafts may be used. Task context is not authority for stored personal facts. Judge the request, not whether the database contains a record. Return only JSON."""
DEPENDENCY_REVIEW_EXAMPLES = (
    ({"current_message": "Which jacket colour did I choose last weekend?", "task_context": []}, True),
    ({"current_message": "I chose a green jacket. Suggest colours for a scarf that matches it.", "task_context": []}, False),
    ({"current_message": "Explain that using an everyday example.", "task_context": [
        {"role": "user", "content": "Explain evaporation."},
        {"role": "assistant", "content": "Evaporation changes liquid into gas."},
    ]}, False),
)


def fragment_candidates(text):
    """Prefer complete requests over suffixes inside noun coordination.

    Sentence boundaries precede conjunctions, earliest first, so multiple
    general clauses can remain together. Conjunction fallback uses the existing
    bounded question/imperative start grammar, never a topic or memory rule.
    """
    sentences = [match.end() for match in re.finditer(r"[.!?;]\s+", text)]
    conjunctions = [match.end() for match in re.finditer(r",?\s+and\s+", text, re.I)]
    candidates = []
    seen = set()
    for start, conjunction in [(start, False) for start in sentences] + [(start, True) for start in conjunctions]:
        if start in seen:
            continue
        seen.add(start)
        general = text[start:].strip()
        personal = re.sub(r"[,;]?\s*and\s*$", "", text[:start], flags=re.I).strip(" ,;")
        if general and personal and len(general) <= 500 and (not conjunction or _QUESTION_START.match(general)):
            candidates.append({"index": len(candidates) + 1, "start": start,
                               "personal_part": personal, "general_part": general})
            if len(candidates) == MAX_CANDIDATES:
                break
    return candidates


def dependency_review_schema():
    return deepcopy(DEPENDENCY_REVIEW_SCHEMA)


def dependency_review_messages(text, history):
    """Do not expose proposed labels, margins, candidate parts or stale facts."""
    messages = [ChatMessage("system", DEPENDENCY_REVIEW_PROMPT)]
    for example, value in DEPENDENCY_REVIEW_EXAMPLES:
        messages.extend((ChatMessage("user", json.dumps(example)),
                         ChatMessage("assistant", json.dumps({"needs_personal_facts": value}))))
    messages.append(ChatMessage("user", json.dumps({
        "current_message": text, "task_context": [message.to_dict() for message in history],
    })))
    return tuple(messages)


def parse_dependency_review(text):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_REVIEW_CHARACTERS:
        raise RoutingError("dependency review response is outside its bounds")
    try:
        value = json.loads(text, object_pairs_hook=_object_without_duplicate_keys)
    except (ValueError, RecursionError) as exc:
        raise RoutingError("dependency review is not valid JSON") from exc
    if (not isinstance(value, dict) or set(value) != {"needs_personal_facts"}
            or type(value["needs_personal_facts"]) is not bool):
        raise RoutingError("dependency review requires one exact Boolean field")
    return value["needs_personal_facts"]
