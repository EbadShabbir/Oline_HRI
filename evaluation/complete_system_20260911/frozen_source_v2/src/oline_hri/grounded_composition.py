"""Small extractive answer builders, not a general-purpose reasoning engine.

Facts arrive only after retrieval/consent checks. Never substitute a named
owner with 'you', invent event dates, or silently cut a fact to fit the budget.
Unsupported requests return None and retain ordinary guarded generation.
"""

from dataclasses import dataclass
from datetime import date
import re
from typing import Optional, Sequence


@dataclass(frozen=True)
class AnswerFact:
    text: str
    when: Optional[date] = None
    date_in_text: bool = False


@dataclass(frozen=True)
class ComposedAnswer:
    speech: str
    constraint: str


def _safe_fact(text: str) -> bool:
    return bool(
        len(text) <= 500
        and re.match(
            r"^(?:(?:I|[Yy]ou|(?:[Tt]he )?[Uu]ser|[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}) "
            r"(?:(?:now|usually) )?(?:prefer|prefers|plan|plans|completed|finished|started|has|have|own|owns|is|are|needs|need|changed)\b|"
            r"(?:[Mm]y|[Yy]our|[A-Z][a-z]+['’]s)\b)", text)
        and not re.search(r'["“”\n\r{}?]|\b(?:if|not|never|maybe|perhaps|might|ignore|instructions?|system|assistant|cancelled|canceled)\b', text, re.I)
    )


def _dated_fact(fact: AnswerFact) -> str:
    if fact.date_in_text:
        return fact.text
    assert fact.when is not None
    return f"{fact.when.strftime('%A')}, {fact.when.isoformat()}: {fact.text}"


def compose_verified_answer(
    facts: Sequence[AnswerFact], request: str, *, named_relationship: bool = False,
    user_relationship: bool = False,
) -> Optional[ComposedAnswer]:
    """Produce one complete, bounded literal answer for a supported intent."""
    if not 1 <= len(facts) <= 3 or not all(_safe_fact(f.text) for f in facts):
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
