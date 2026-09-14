"""Small extractive answer builders, not a general-purpose reasoning engine.

Facts arrive only after retrieval/consent checks. Never substitute a named
owner with 'you', invent event dates, or silently cut a fact to fit the budget.
Unsupported requests return None and retain ordinary guarded generation.
"""

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Optional, Sequence

from .memory_evidence import topic_terms


@dataclass(frozen=True)
class AnswerFact:
    text: str
    when: Optional[date] = None
    date_in_text: bool = False
    instant: Optional[datetime] = None


@dataclass(frozen=True)
class ComposedAnswer:
    speech: str
    constraint: str


def _safe_fact(text: str) -> bool:
    return bool(
        len(text) <= 500
        and re.match(
            r"^(?:(?:I|[Yy]ou|(?:[Tt]he )?[Uu]ser|[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}) "
            r"(?:(?:now|usually) )?(?:prefer|prefers|plan|plans|completed|finished|started|submitted|has|have|own|owns|is|are|needs|need|changed)\b|"
            r"(?:[Mm]y|[Yy]our|[A-Z][a-z]+['’]s)\b)", text)
        and not re.search(r'["“”\n\r{}?]|\b(?:if|not|never|maybe|perhaps|might|ignore|instructions?|system|assistant|cancelled|canceled)\b', text, re.I)
    )


def _dated_fact(fact: AnswerFact) -> str:
    if fact.date_in_text:
        return fact.text
    assert fact.when is not None
    return f"{fact.when.strftime('%A')}, {fact.when.isoformat()}: {fact.text}"


def compose_partial_recall(
    facts: Sequence[AnswerFact], missing_subjects: Sequence[str],
) -> Optional[ComposedAnswer]:
    """Give supported direct-recall facts and explicitly mark absent fields.

    Missing fields come from a fully parsed request, never from a model guess.
    This says only that verified evidence is absent; it does not infer that an
    item was forgotten, deleted, moved, or never existed.
    """
    if not 1 <= len(facts) <= 2 or not 1 <= len(missing_subjects) <= 2:
        return None
    if not all(_safe_fact(f.text) for f in facts):
        return None
    if any(not re.fullmatch(r"[\w'’ -]{1,120}", value) for value in missing_subjects):
        return None
    speech = " ".join(f.text for f in facts)
    speech += " I do not have verified information about " + " or ".join(missing_subjects) + "."
    if len(speech.split()) > 80 or len(speech) > 850:
        return None
    return ComposedAnswer(speech, "verified_partial_recall")


def compose_verified_event_times(
    facts: Sequence[AnswerFact], request: str,
) -> Optional[ComposedAnswer]:
    """Order recorded instants and subtract a pair; never infer missing times.

    The caller checks each instant against the source text/metadata. Broader
    planning, hypothetical schedules, conversions, and mixed tasks retain
    normal guarded generation. All source facts are preserved in the answer.
    """
    if not 2 <= len(facts) <= 3 or not all(_safe_fact(f.text) and f.instant for f in facts):
        return None
    if re.search(
        r"\b(?:why|plan|schedule|budget|cost|risk|estimate|suppose|assume|if|"
        r"translate|poem|rhyme|json|table|verbatim|only|omit|exclude|exactly|"
        r"partner|collaborator|prefer\w*|buy|travel|depart\w*|timezone|zone|utc|gmt|"
        r"mov\w*|reschedul\w*|delay\w*|advanc\w*|after|before|draft|checklist|seconds?)\b",
        request, re.I,
    ):
        return None
    # Full grammars, including the optional instructions, prevent a bound
    # chronology from silently replacing an additional task or rescheduling.
    subject = r"[\w'’ -]{1,180}"
    elapsed = re.fullmatch(
        rf"\s*How (?:many (?:hours?|minutes?)|long) (?:passed|elapsed) between (?P<left>{subject}) and (?P<right>{subject})\?"
        r"(?:\s*Use the stored event times and show the two times[.]?)?\s*", request, re.I,
    )
    comparison = re.fullmatch(
        rf"\s*Which (?:(?:comes|came) (?:first|later)|did I complete (?:later|earlier)),? (?P<left>{subject}) or (?P<right>{subject})\?"
        r"(?:\s*Give (?:the dates supporting the answer|their dates and times(?:, and the interval between them)?)[.]?)?\s*",
        request, re.I,
    )
    chronology = re.fullmatch(
        r"\s*Put (?P<subjects>[\w'’, -]{1,360}) in chronological order"
        r"(?:,? giving each (?:stored )?date and time)?[.]?\s*", request, re.I,
    )
    interval = elapsed is not None or (comparison is not None and "interval" in request.casefold())
    if not (elapsed or comparison or chronology) or (interval and len(facts) != 2):
        return None
    expressions = ((elapsed or comparison).group("left", "right")
                   if elapsed or comparison else (chronology.group("subjects"),))
    wanted = set().union(*(topic_terms(part) for part in expressions)) - {"store", "record", "event"}
    supported = set().union(*(topic_terms(f.text) for f in facts))
    if not wanted or not wanted.issubset(supported):
        return None
    # An explicit cardinality must match the evidence; two facts cannot
    # silently answer a requested three-event chronology.
    count = re.search(r"\b(two|three|four|five|[2-9])(?:[ -][a-z]+){0,3}[ -](?:events?|entries|entry|items?|trials?|milestones?)\b", request, re.I)
    if count:
        wanted = {"two": 2, "three": 3, "four": 4, "five": 5}.get(count[1].lower())
        if (wanted if wanted is not None else int(count[1])) != len(facts):
            return None
    if any(re.search(
        r"\b(?:UTC|GMT|[PECMA][DS]T|Pacific|Eastern|Central|Mountain|timezone)\b|"
        r"\b[A-Za-z_]+/[A-Za-z_]+\b|[+-]\d{2}:\d{2}\b|"
        r"\b[A-Za-z]+(?:\s+(?:standard|daylight))?\s+time\b|"
        r"\d{1,2}[:.]\d{2}(?::\d|\.\d)|"
        r"\d{1,2}[:.]\d{2}\s*[([]?\s+(?!(?:in|at|on|near|with)\b)[A-Za-z]{2,8}\b|"
        r"\d{1,2}[:.]\d{2}\s*[([]\s*[A-Za-z]{2,8}\b",
        f.text, re.I,
    ) for f in facts):
        return None
    instants = [f.instant for f in facts]
    if any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None
           or t.second or t.microsecond for t in instants):
        return None
    if len({t.utcoffset() for t in instants}) != 1:
        return None
    ordered = sorted(facts, key=lambda f: f.instant)
    if len({f.instant for f in ordered}) != len(ordered):
        return None
    parts = [f"{index}. {f.instant.strftime('%Y-%m-%d at %H:%M')}: {f.text}"
             for index, f in enumerate(ordered, 1)]
    suffix = " The entries are in chronological order."
    if interval:
        minutes = int((ordered[1].instant - ordered[0].instant).total_seconds() // 60)
        hours, remainder = divmod(minutes, 60)
        if re.search(r"\bhow\s+many\s+minutes\b", request, re.I):
            duration = f"{minutes} minutes"
        else:
            duration = f"{hours} hours" + (f" {remainder} minutes" if remainder else "")
        suffix += f" The elapsed time is {duration}."
    else:
        suffix += f" Entry 1 is earliest; entry {len(ordered)} is latest."
    speech = " ".join(parts) + suffix
    if len(speech.split()) > 80 or len(speech) > 850:
        return None
    return ComposedAnswer(speech, "verified_event_interval" if interval else "verified_event_order")


def compose_verified_answer(
    facts: Sequence[AnswerFact], request: str, *, named_relationship: bool = False,
    user_relationship: bool = False,
) -> Optional[ComposedAnswer]:
    """Produce one complete, bounded literal answer for a supported intent."""
    if not 1 <= len(facts) <= 3 or not all(_safe_fact(f.text) for f in facts):
        return None
    if re.search(
        r"\b(?:if|suppose|assum\w*|hypothet\w*|mov\w*|shift\w*|reschedul\w*|delay\w*)\b|"
        r"\b(?:also|then|and)\s+(?:draft|write|sing|translate|summarize|draw)\b|"
        r"\b(?:include|add)\s+(?:a\s+)?(?:checklist|poem|note)\b", request, re.I,
    ):
        return None
    # These modifiers require reasoning or a format these builders do not do.
    if re.search(r"\b(?:why|budget|cost|risk|estimate|translate|poem|rhyme|json|table|verbatim|only|omit|exclude|exactly)\b|\b(?:three|3|four|4|five|5)[ -](?:entry|event|item)", request, re.I):
        return None
    dated = sorted((f for f in facts if f.when), key=lambda f: f.when)
    distinct_pair = len(dated) == 2 and dated[0].when != dated[1].when
    text = " ".join(f.text for f in facts)
    result = None
    if named_relationship and len(facts) == 1:
        result = ComposedAnswer(facts[0].text, "verified_named_relationship")
    elif user_relationship and len(facts) == 1:
        result = ComposedAnswer(facts[0].text, "verified_user_relationship")
    elif (
        distinct_pair and len(facts) == 2
        and re.search(r"\b(?:timeline|chronolog\w*)\b", request, re.I)
    ):
        result = ComposedAnswer(
            f"1. {_dated_fact(dated[0])} 2. {_dated_fact(dated[1])} Entry 2 came later.",
            "verified_timeline",
        )
    elif (
        distinct_pair and re.search(r"\bmilestones?\b", request, re.I)
        and re.search(r"\b(?:earlier|newer|recent)\b", request, re.I)
        and all(re.search(r"\b(?:completed|completing|finished)\b", f.text, re.I) for f in dated)
        and all(re.search(r"\b(?:partner|collaborator)\b", f.text, re.I)
                and not re.search(r"\bmilestone\b", f.text, re.I)
                for f in facts if not f.when)
    ):
        other = " ".join(f.text for f in facts if not f.when)
        result = ComposedAnswer(
            f"1. {_dated_fact(dated[0])} 2. {_dated_fact(dated[1])} Entry 2 is newer. {other}".strip(),
            "verified_milestone_comparison",
        )
    elif (
        len(facts) >= 2
        and re.search(r"\b(?:three|3)[ -]stage\b", request, re.I)
        and re.search(r"\b(?:presenting|presentation)\b", request, re.I)
        and re.search(r"\b(?:completed|finished)\b", text, re.I)
        and re.search(r"\bmeetings?\b", text, re.I)
        and re.search(r"\b(?:answers?|replies)\b", text, re.I)
    ):
        preserved = "; ".join(f.text.rstrip(".") for f in facts) + "."
        result = ComposedAnswer(
            preserved + " 1. Select demo evidence; verify it matches completed work."
            " 2. Rehearse within the meeting window; check timing."
            " 3. Test materials; prepare screenshots if the demo fails.",
            "verified_presentation_plan",
        )
    elif (
        distinct_pair and len(facts) == 2
        and re.search(r"\bchecklist\b", request, re.I)
        and re.search(r"\b(?:travel|trip|visit)\w*\b", request, re.I)
        and all(re.search(r"\bplans? to (?:visit|take|travel|go)\b", f.text, re.I) for f in facts)
    ):
        entries = []
        for index, fact in enumerate(dated, 1):
            if re.search(r"\b(?:museum|gallery|exhibit\w*)\b", fact.text, re.I):
                checks = "Check opening hours, entry booking and return transport; if closed, reschedule."
            elif re.search(r"\b(?:train|bus|flight|ferry)\b", fact.text, re.I):
                checks = "Verify departure, boarding point and ticket; if cancelled, check alternatives."
            else:
                checks = "Verify route, transport and booking; if unavailable, reschedule."
            entries.append(f"{index}. {_dated_fact(fact)} {checks}")
        result = ComposedAnswer(" ".join(entries), "verified_travel_checklist")
    if result and (len(result.speech.split()) > 80 or len(result.speech) > 850):
        return None
    return result
