"""Conservative fidelity checks for editing an explicitly supplied draft.

This module does not find, admit, or recall history. ``admitted_source`` must
already be an application-admitted written artifact, never a personal record or
an arbitrary assistant message. Without it, only one quoted source in the
current editing request is considered. These lexical checks catch omissions and
concrete changes; passing them does not establish semantic equivalence.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re


_QUOTED = re.compile(r'"([^"\n]+)"|“([^”\n]+)”|(?<!\w)\'([^\'\n]+)\'(?!\w)')
_EDIT = re.compile(
    r"^(?:please\s+)?(?:shorten|condense|rewrite|rephrase|tighten|edit|"
    r"make\s+(?:it|that|this|the\s+(?:announcement|invitation|note|message|draft|text))"
    r"\s+(?:shorter|more\s+concise|clearer|more\s+formal|less\s+formal))\b", re.I)
_PERSONAL = re.compile(
    r"\b(?:my|mine|his|her|their|your|yours|remember|recall|remind|"
    r"remembered|guessed|guess|assumed|diagnosis|password|birthday|address)\b|"
    r"\bi\s+(?:am|was|have|had|think|thought|believe|said|told|chose)\b", re.I)
_DIFFERENT_ARTIFACT = re.compile(
    r"\b(?:instead\s+(?:write|create|make)|(?:new|different)\s+(?:event|subject|topic)|"
    r"(?:as|into)\s+(?:(?:a|an)\s+)?(?:poem|story|fiction|dialogue|song))\b", re.I)
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_DAY = r"(?:(?i:" + "|".join(_DAYS) + r")|Mon\.?|Tue(?:s)?\.?|Wed\.?|Thu(?:rs?)?\.?|Fri\.?|Sat\.?|Sun\.?)"
_DAY_RE = re.compile(r"\b(" + _DAY + r")(?!\w)")
_TIME_RE = re.compile(
    r"\b(?:noon|midday|midnight|\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?|\d{1,2}:\d{2})(?!\w)", re.I)
_LOCATION_RE = re.compile(
    r"\b(room|studio|hall|suite|lab(?:oratory)?|auditorium|building|gate)\s*"
    r"(?:(?:no\.?|number|#)\s*)?([A-Za-z]?\d+[A-Za-z]?)(?!\w)", re.I)
_NUMBER_WORDS = dict(enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()))
_NUMBER_VALUES = {word: value for value, word in _NUMBER_WORDS.items()}
_NUMBER = r"(?:\d{1,3}|" + "|".join(_NUMBER_VALUES) + r")"


@dataclass(frozen=True)
class DraftContract:
    """Only source-derived anchors and explicit request constraints."""

    max_words: int | None
    weekdays: tuple[str, ...]
    times: tuple[tuple[int, int], ...]
    locations: tuple[tuple[str, str], ...]
    subject_terms: tuple[str, ...]
    weekday_move: tuple[str, str] | None


def _day(value: str) -> str:
    return next(day for day in _DAYS if day.casefold().startswith(value[:3].casefold()))


def _weekdays(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_day(match.group(1)) for match in _DAY_RE.finditer(text)))


def _times(text: str) -> tuple[tuple[int, int], ...]:
    values = []
    for match in _TIME_RE.finditer(text):
        value = re.sub(r"\s+", "", match.group().casefold().replace(".", ""))
        if value in {"noon", "midday", "midnight"}:
            result = (0 if value == "midnight" else 12, 0)
        else:
            clock = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?([ap]m)?", value)
            hour, minute = int(clock[1]), int(clock[2] or 0)
            meridiem = clock[3]
            if minute > 59 or hour > 23 or meridiem and not 1 <= hour <= 12:
                continue
            if meridiem:
                hour = hour % 12 + (12 if meridiem == "pm" else 0)
            result = (hour, minute)
        if result not in values:
            values.append(result)
    return tuple(values)


def _locations(text: str) -> tuple[tuple[str, str], ...]:
    values = []
    for match in _LOCATION_RE.finditer(text):
        kind, number = match.group(1).casefold(), match.group(2).casefold()
        value = ("lab" if kind == "laboratory" else kind, number)
        if value not in values:
            values.append(value)
    return tuple(values)


def _moves(text: str) -> tuple[tuple[str, str], ...]:
    # Only explicit direction constructions are interpreted. Mere mention order
    # cannot distinguish "Thursday, previously Tuesday" from the reverse move.
    values = []
    for pattern, reverse in (
        (r"\bfrom\s+(" + _DAY + r")\s+to\s+(" + _DAY + r")", False),
        (r"\bto\s+(" + _DAY + r")\s+from\s+(" + _DAY + r")", True),
        (r"\b(" + _DAY + r")\s+(?:instead\s+of|rather\s+than|replaces)\s+(" + _DAY + r")", True),
        (r"\b(" + _DAY + r")\s*(?:→|->)\s*(" + _DAY + r")", False),
    ):
        for match in re.finditer(pattern, text, re.I):
            pair = (_day(match[1]), _day(match[2]))
            values.append(pair[::-1] if reverse else pair)
    return tuple(dict.fromkeys(values))


def _max_words(request: str) -> int | None:
    values = set()
    for pattern, offset in (
        (r"\b(?:no\s+more\s+than|at\s+most|up\s+to|maximum(?:\s+of)?)\s+(" + _NUMBER + r")\s+words?\b", 0),
        (r"\b(" + _NUMBER + r")\s+words?\s+(?:or\s+(?:fewer|less)|maximum|at\s+most)\b", 0),
        (r"\b(?:under|fewer\s+than|less\s+than)\s+(" + _NUMBER + r")\s+words?\b", -1),
        (r"<=\s*(" + _NUMBER + r")\s+words?\b", 0),
    ):
        for match in re.finditer(pattern, request, re.I):
            token = match[1].casefold()
            value = (int(token) if token.isdigit() else _NUMBER_VALUES[token]) + offset
            if 1 <= value <= 200:
                values.add(value)
    return values.pop() if len(values) == 1 else None


def _changed(request: str, category: str) -> bool:
    targets = {
        "weekdays": r"\b(?:weekdays?|days?|dates?)\b|" + _DAY_RE.pattern,
        "times": r"\b(?:times?|hours?)\b|" + _TIME_RE.pattern,
        "locations": r"\b(?:rooms?|studios?|halls?|suites?|labs?|laboratories|locations?|venues?|buildings?|gates?)\b",
        "subject": r"\b(?:subject|topic|event)\b",
    }
    for clause in re.split(r"[.!?;]|\b(?:and|but|while)\b", request, flags=re.I):
        change = re.search(r"\b(?:change|replace|switch|move|reschedule|set|omit|remove|drop)\b", clause, re.I)
        if change and re.search(r"\b(?:not|never|don't|no)\s*$", clause[:change.start()], re.I):
            continue
        if change and re.search(targets[category], clause, re.I):
            return True
    return False


def _subject(source: str) -> tuple[str, ...]:
    value = re.sub(r"^\s*(?:(?:please\s+)?note\s+that\s+|please\s+note[:,]?\s+)", "", source, flags=re.I)
    match = re.match(
        r"(?:(?:our|the|this|a|an)\s+)?([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,4}?)\s+"
        r"(?:has\s+(?:been\s+)?moved|is\s+(?:being\s+)?(?:moved|moving)|"
        r"(?:has\s+been\s+|is\s+)?rescheduled|moves?|moved|will\s+(?:take\s+place|be\s+held)|"
        r"takes\s+place|starts?|begins?|meets?|is\s+(?:on|at))\b", value, re.I)
    if not match:
        return ()
    return tuple(word.casefold() for word in match[1].split()
                 if word.casefold() not in {"our", "the", "this", "a", "an", "and", "of", "for"})


def draft_contract(request: str, admitted_source: str | None = None) -> DraftContract | None:
    """Build a contract for a supplied quote or an already admitted artifact.

    Callers must select the actual requested draft before passing
    ``admitted_source``. This function deliberately accepts no history list and
    cannot resolve multiple drafts or turn prior personal facts into sources.
    Explicit changes disable checks for that category, because its old value is
    no longer a preservation requirement.
    """
    if not isinstance(request, str) or len(request) > 4096 or not _EDIT.search(request.strip()):
        return None
    quotes = list(_QUOTED.finditer(request))
    directive = _QUOTED.sub(" ", request)
    if _PERSONAL.search(directive) or _DIFFERENT_ARTIFACT.search(directive) or _changed(directive, "subject"):
        return None
    source_quotes = [next(group for group in match.groups() if group is not None)
                     for match in quotes if len(match.group().split()) >= 3]
    if source_quotes:
        if len(source_quotes) != 1:
            return None
        source = source_quotes[0]
    else:
        source = admitted_source
    if (not isinstance(source, str) or not source.strip() or len(source) > 4096
            or _PERSONAL.search(source)
            or re.search(r"\b(?:maybe|perhaps|possibly|probably|might|could)\b", source, re.I)):
        return None
    weekdays = () if _changed(directive, "weekdays") else _weekdays(source)
    times = () if _changed(directive, "times") else _times(source)
    locations = () if _changed(directive, "locations") else _locations(source)
    # Preserve an event subject only when the source has concrete event anchors.
    # Arbitrary prose is not reduced to a list of words that must be copied.
    subject = _subject(source) if weekdays or times or locations else ()
    moves = _moves(source) if weekdays else ()
    contract = DraftContract(_max_words(directive), weekdays, times, locations,
                             subject, moves[0] if len(moves) == 1 else None)
    return contract if any((contract.max_words, weekdays, times, locations, subject)) else None


def draft_instruction(contract: DraftContract | None) -> str:
    """Application-owned source anchors for initial generation and one retry."""
    if contract is None:
        return ""
    rules = ["Edit the supplied draft faithfully."]
    if contract.max_words is not None:
        rules.append(f"Use no more than {contract.max_words} whitespace-separated words.")
    if contract.subject_terms:
        rules.append("Keep the event subject: " + json.dumps(" ".join(contract.subject_terms)) + ".")
    if contract.weekdays:
        rules.append("Preserve these weekdays: " + ", ".join(contract.weekdays) + ".")
    if contract.weekday_move:
        rules.append(f"The move is FROM {contract.weekday_move[0]} TO {contract.weekday_move[1]}; do not reverse it.")
    if contract.times:
        times = ", ".join(f"{hour:02d}:{minute:02d}" for hour, minute in contract.times)
        rules.append(f"Preserve the time(s): {times} (equivalent clock wording is allowed).")
    if contract.locations:
        places = ", ".join(f"{kind} {number}" for kind, number in contract.locations)
        rules.append(f"Preserve the location(s): {places}.")
    return " ".join(rules)


def draft_contract_issues(contract: DraftContract | None, answer: str) -> tuple[str, ...]:
    """Check concrete omissions, extra anchors, explicit reversal and word cap."""
    if contract is None:
        return ()
    issues = []
    if contract.max_words is not None and len(answer.split()) > contract.max_words:
        issues.append("draft_word_limit")
    if contract.weekdays and set(_weekdays(answer)) != set(contract.weekdays):
        issues.append("draft_weekdays")
    if contract.times and set(_times(answer)) != set(contract.times):
        issues.append("draft_time")
    if contract.locations and set(_locations(answer)) != set(contract.locations):
        issues.append("draft_location")
    words = set(re.findall(r"[A-Za-z][A-Za-z'-]*", answer.casefold()))
    if contract.subject_terms and not set(contract.subject_terms).issubset(words):
        issues.append("draft_subject")
    if contract.weekday_move and any(move != contract.weekday_move for move in _moves(answer)):
        issues.append("draft_move_direction")
    return tuple(issues)
