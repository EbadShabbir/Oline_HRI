"""Bounded lexical evidence signals, without another model or embedding call.

These signals rank already-authorized retrieval candidates. They never grant
consent, bypass lifecycle checks, or turn semantic similarity into a fact.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Sequence
import unicodedata


_STOP = frozenset(
    "a about all also an and answerable are as at be been both by can could "
    "create detailed did do does during each earlier every everything exact "
    "explicitly fact for from had has have how i identify in into is it its "
    "keep know later me memory most my name named newer next note of on or our "
    "please preparation present presenting recent recall remember say she "
    "stage still tell than that the these this those three to two use using "
    "was we were what when where which who will with would you your "
    "compare comparing chronological chronology timeline explain build "
    "checklist distinct length window plan".split()
)
_COLORS = frozenset(
    "black blue brown cyan gold gray green grey indigo ivory magenta maroon "
    "orange pink purple red silver teal turquoise violet white yellow".split()
)


def relevance_stem(value: str) -> str:
    """Normalize a small, shared set of English inflections and synonyms."""
    token = value.casefold()
    if token in {"collaborator", "collaborators"}:
        return "partner"
    if token in {"bike", "bikes", "bicycles"}:
        return "bicycle"
    if token in {
        "complete", "completed", "completing", "completion", "completions",
        "finish", "finished", "finishing",
    }:
        return "complete"
    if token in {
        "enjoy", "enjoyed", "enjoys", "favorite", "favorites", "favourite",
        "favourites", "like", "liked", "likes", "preference", "preferences",
        "preferred", "prefers",
    }:
        return "prefer"
    if len(token) > 4 and token.endswith("ies"):
        token = token[:-3] + "y"
    elif len(token) > 3 and token.endswith("s"):
        token = token[:-1]
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
        if len(token) > 2 and token[-1] == token[-2]:
            token = token[:-1]
    elif len(token) > 4 and token.endswith("ed"):
        token = token[:-2]
    return token


def topic_terms(text: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"['’]s\b", "", normalized)
    return frozenset(
        relevance_stem(word)
        for word in re.findall(r"[^\W_]+", normalized)
        if len(word) > 1 and word not in _STOP
        and relevance_stem(word) not in _STOP
    )


def direct_subject_supported(query: str, text: str) -> bool | None:
    """Require the requested object, not merely its surrounding topic.

Return None outside a few explicit direct-question grammars. Attribute slots
also require evidence of that attribute; owning a bike does not reveal color.
"""
    normalized = unicodedata.normalize("NFKC", query).replace("’", "'")
    broad = re.fullmatch(
        r"\s*(?:(?:what\s+do\s+you\s+(?:remember|recall))|"
        r"(?:(?:please\s+)?(?:tell|remind)\s+me\s+what\s+you\s+"
        r"(?:remember|recall)))\s+about\s+my\s+"
        r"(?P<subject>[\w -]+)[?.!]*\s*", normalized, re.I,
    )
    if broad is not None:
        subject_terms = topic_terms(broad.group("subject"))
        if subject_terms:
            return subject_terms.issubset(topic_terms(text))
        return None
    match = re.fullmatch(
        r"\s*(?:what|which)\s+(?P<slot>colou?r|name)\s+"
        r"(?:is|was)\s+my\s+(?P<subject>[\w -]+)[?.!]*\s*",
        normalized, re.I,
    )
    slot = None
    if match is not None:
        slot, subject = match.group("slot").lower(), match.group("subject")
    else:
        match = re.fullmatch(
            r"\s*what\s+is\s+my\s+(?P<subject>[\w -]+)'s\s+name[?.!]*\s*",
            normalized, re.I,
        )
        if match is not None:
            slot, subject = "name", match.group("subject")
        else:
            match = re.match(
                r"\s*(?:what|which)\s+(?:kind\s+of\s+|type\s+of\s+)?"
                r"(?P<subject>\w+)\s+(?:do|did|have|had|is|are)\b",
                normalized, re.I,
            )
            if match is None:
                return None
            subject = match.group("subject")
            if subject.casefold() in {
                "time", "day", "date", "way", "else", "information",
                "fact", "facts", "memory", "memories",
            }:
                return None
    wanted = topic_terms(subject)
    if not wanted:
        return None
    available = topic_terms(text)
    if not wanted.issubset(available):
        return False
    if slot in {"color", "colour"}:
        colors = "|".join(sorted(_COLORS))
        # A green helmet beside a bicycle does not supply the bicycle's color.
        subject_head = relevance_stem(subject.split()[-1])
        head = r"(?:bike|bicycle)" if subject_head == "bicycle" else re.escape(subject_head)
        return bool(re.search(
            rf"\b(?:{colors})\s+{head}\b|"
            rf"\b{head}\s+(?:is|was)\s+(?:{colors})\b", text, re.I
        ))
    if slot == "name":
        return re.search(r"\b(?:named|called|name\s+is)\b", text, re.I) is not None
    return True


def evidence_order(query: str, texts: Sequence[str]) -> tuple[int, ...]:
    """Rerank the bounded RRF pool by topic coverage, using RRF to break ties.

For synthesis, discount already-covered terms so one topic cannot occupy all
three slots. For direct questions retain equal-facet candidates, including
conflicts. Empty lexical evidence leaves the original RRF ranking unchanged.
"""
    wanted = topic_terms(query)
    terms = [topic_terms(text) for text in texts]
    counts = Counter(term for item in terms for term in item)
    weights = {term: 1.0 / counts[term] for term in wanted if counts[term]}
    multiple = bool(re.search(
        r"\b(?:and|both|compare|timeline|summarize)\b", query, re.I
    ))
    remaining = list(range(len(texts)))
    ordered = []
    covered: set[str] = set()
    while remaining:
        def key(index):
            overlap = wanted & terms[index]
            support = direct_subject_supported(query, texts[index])
            score = sum(
                weights[term] * (0.35 if multiple and term in covered else 1)
                for term in overlap
            )
            return (support is not False, score, -index)

        best = max(remaining, key=key)
        remaining.remove(best)
        ordered.append(best)
        covered.update(wanted & terms[best])
    return tuple(ordered)
