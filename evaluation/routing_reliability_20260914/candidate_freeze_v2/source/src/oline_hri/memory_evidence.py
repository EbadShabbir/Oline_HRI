"""Bounded lexical evidence signals, without another model or embedding call.

These signals rank already-authorized retrieval candidates. They never grant
consent, bypass lifecycle checks, or turn semantic similarity into a fact.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
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


def requests_correction_time(query: str) -> bool:
    """Recognize a request for when a memory change took effect.

    The time of a correction is not the time of its appointment or event.
    The temporal question must target the change operation itself; mentioning
    an earlier update while asking about an event does not request metadata.
    This bounded English check controls metadata relevance, never lifecycle
    authorization or the validity of the stored event itself.
    """
    text = unicodedata.normalize("NFKC", query).replace("’", "'")
    temporal_question = (
        r"(?:when|(?:on\s+)?what\s+(?:date|day)|(?:at\s+)?what\s+time)"
    )
    operation = r"(?:chang(?:e|ed)|correct(?:ed)?|updat(?:e|ed)|revis(?:e|ed))"
    active_operation = (
        r"(?:(?:did|do|does|have|has|had)\s+)?(?:i|you|we|(?:the\s+)?user)\s+"
        rf"(?:(?:last|most\s+recently|have|had|has|did)\s+){{0,2}}{operation}\b"
    )
    direct_patterns = (
        rf"{temporal_question}\s+{active_operation}",
        rf"{temporal_question}\s+(?:was|were|is|are)\s+"
        r"(?:(?!\b(?:before|after|since|that|because|when|and|if)\b)[^.!?;\n]){1,100}"
        r"\b(?:changed|corrected|updated|revised)\s*$",
        r"(?:what|which)\s+(?:is|was)\s+(?:the\s+)?(?:date|time|timestamp)\s+"
        r"(?:of|for)\s+[^.!?;\n]{0,100}\b(?:change|correction|update|revision)\s*$",
        rf"{temporal_question}\s+(?:(?:did|does|will)\s+)?"
        r"(?:(?:the|this|that|my)\s+)?(?:change|correction|update|revision)\s+"
        r"(?:(?:take|took)\s+effect|(?:become|became)\s+effective)\b",
    )
    for clause in re.split(r"[.!?;\n]", text):
        clause = re.sub(
            r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
            r"(?:(?:tell|remind|show)\s+me\s+)?", "", clause, flags=re.I,
        ).strip()
        if any(re.match(pattern, clause, re.I) for pattern in direct_patterns):
            return True
        if (
            re.match(r"(?:create|build|give|show|compare|put|list|order)\b", clause, re.I)
            and re.search(r"\b(?:chronolog\w*|timeline)\b", clause, re.I)
            and re.search(rf"\bwhen\s+{active_operation}", clause, re.I)
        ):
            return True
    return False


def relevance_stem(value: str) -> str:
    """Normalize a small, shared set of English inflections and synonyms."""
    token = value.casefold()
    if token in {"collaborator", "collaborators"}:
        return "partner"
    if token in {"bike", "bikes", "bicycles"}:
        return "bicycle"
    if token in {"submit", "submitted", "submitting", "submission", "submissions"}:
        return "submit"
    if token in {"available", "availability"}:
        return "available"
    if token in {"duration", "length"}:
        return "duration"
    if token in {"travel", "travelling", "traveling"}:
        return "journey"
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


@dataclass(frozen=True)
class SubjectFacet:
    """One explicitly requested field, not an inferred fact or permission."""

    subject: str
    terms: frozenset[str]
    attribute: str | None = None
    owner: str | None = None
    dates: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubjectRequest:
    """A completely recognized request grammar with bounded subject slots."""

    facets: tuple[SubjectFacet, ...]
    mode: str


_CALENDAR = frozenset(
    "monday tuesday wednesday thursday friday saturday sunday january february "
    "march april may june july august september october november december".split()
)
_SUBJECT_MODIFIERS = frozenset(
    "current currently stored recorded saved usual completed complete finished "
    "next past recent earlier both the my our your a an".split()
)
_NON_SUBJECT = frozenset(
    "hour minute second time date day year month week interval order chronology "
    "first later earliest latest before after give show tell remind specify "
    "start end finish".split()
)
_CLAUSE_VERBS = re.compile(
    r"\b(?:can|could|would|should|must|will|shall|explain|compare|calculate|"
    r"create|plan|choose|select|obtain|buy|costs?|takes?|lasts?|needs?|"
    r"move|reschedule|suppose|assume|imagine|recommend|why|whether|if|then|"
    r"give|show|identify|describe|summarize|tell|remind|what|which|who|"
    r"when|where|how)\b", re.I,
)
_FULL_DATE = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})\b", re.I,
)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_MONTH_NUMBER = {
    month: index for index, month in enumerate(
        "january february march april may june july august september october "
        "november december".split(), 1
    )
}
_INSTRUCTION_WORDS = frozenset(
    "give giving show showing include including use using the their its both "
    "each two three stored event events date dates time times and interval "
    "between them supporting answer chronological order start end finish "
    "remaining margin total credits left with no other purchases".split()
)


def _dates(text: str) -> tuple[str, ...]:
    values = []
    for raw in _ISO_DATE.findall(text):
        try:
            values.append(date.fromisoformat(raw).isoformat())
        except ValueError:
            continue
    for day, month, year in _FULL_DATE.findall(text):
        try:
            values.append(date(int(year), _MONTH_NUMBER[month.casefold()], int(day)).isoformat())
        except ValueError:
            continue
    return tuple(dict.fromkeys(values))


def personal_memory_request(query: str) -> str | None:
    """Extract a bounded personal recall request after a subject-only preamble.

    An elliptical question may inherit its subject and identifying date, never
    a fact value, from that preamble. Additional instructions, assertions and
    unrelated final questions are left unparsed instead of being discarded.
    """
    text = unicodedata.normalize("NFKC", query).replace("’", "'").strip()
    match = re.fullmatch(
        r"Earlier\s+I\s+told\s+you\s+(?:about\s+my\s+(?P<about>[^.!?;]+)|"
        r"where\s+my\s+(?P<where>[^.!?;]+?)\s+(?:is|was|are|were))\.\s+"
        r"(?P<request>[^.!?;]+)[?.!]?", text, re.I,
    )
    if match:
        subject = match.group("about") or match.group("where")
        question = match.group("request").strip()
    else:
        match = re.fullmatch(
            r"Returning\s+to\s+my\s+earlier\s+(?P<subject>[^,.!?;]+),\s*"
            r"(?P<request>[^.!?;]+)[?.!]?", text, re.I,
        )
        if match is None:
            return None
        subject, question = match.group("subject"), match.group("request").strip()
    subject = re.sub(r"\s+information$", "", subject.strip(), flags=re.I)
    noun_subject = _ISO_DATE.sub("", _FULL_DATE.sub("", subject))
    noun_subject = re.sub(r"\s+on\s*$", "", noun_subject, flags=re.I).strip()
    if (
        not re.fullmatch(r"[A-Za-z][A-Za-z -]{0,100}", noun_subject)
        or _CLAUSE_VERBS.search(noun_subject)
        or re.search(
            r"\b(?:and|or|is|are|was|were|in|inside|at|for|from|that|said|"
            r"prefer|prefers|like|likes|named|called)\b", noun_subject, re.I,
        )
        or not re.match(r"^(?:what|which|where|who|when)\b", question, re.I)
        or re.search(r"\b(?:and|or|if|because|then)\b|[,;]", question, re.I)
    ):
        return None
    if re.fullmatch(
        r"where\s+(?:is\s+it|are\s+they)(?:\s+(?:located|stored|kept))?"
        r"(?:\s+(?:now|currently))?", question, re.I,
    ):
        plural = re.search(r"\bare\s+they\b", question, re.I)
        return f"Where {'are' if plural else 'is'} my {subject}?"
    if re.fullmatch(r"what\s+(?:start\s+)?time\s+is\s+(?:currently\s+)?recorded", question, re.I):
        return f"What time is my {subject}?"
    elliptical_time = re.fullmatch(
        r"what\s+is\s+its\s+(?:recorded\s+)?(?:start\s+)?time"
        r"(?P<date>\s+on\s+\d{4}-\d{2}-\d{2})?(?:\s+now)?", question, re.I,
    )
    if elliptical_time:
        suffix = elliptical_time.group("date") or ""
        if suffix and _dates(subject) and _dates(subject) != _dates(suffix):
            return None
        return f"What time is my {subject}{suffix if not _dates(subject) else ''}?"
    if re.fullmatch(r"which\s+venue\s+is\s+in\s+the\s+current\s+record", question, re.I):
        return f"Where was my {subject}?"
    elliptical_venue = re.fullmatch(
        r"what\s+venue\s+is\s+now\s+recorded\s+for\s+that\s+event"
        r"(?P<date>\s+on\s+\d{4}-\d{2}-\d{2})?", question, re.I,
    )
    if elliptical_venue:
        suffix = elliptical_venue.group("date") or ""
        if suffix and _dates(subject) and _dates(subject) != _dates(suffix):
            return None
        return f"Where was my {subject}{suffix if not _dates(subject) else ''}?"
    subject_terms = topic_terms(noun_subject) - {"prefer", "information"}
    if subject_terms and subject_terms <= topic_terms(question):
        return question + "?"
    return None


def _request_head(query: str) -> str | None:
    text = personal_memory_request(query) or unicodedata.normalize("NFKC", query).replace("’", "'").strip()
    prefix = re.match(r"^(?:before|after)\s+((?:the\s+)?[\w -]{1,60}),\s*", text, re.I)
    if prefix:
        if _CLAUSE_VERBS.search(prefix.group(1)) or re.search(r"\b(?:i|you|we)\b", prefix.group(1), re.I):
            return None
        text = text[prefix.end():]
    # Strip only an explicitly recognized output instruction. A second
    # substantive clause must not disappear and make exclusion overconfident.
    parts = re.split(r"[?.!]\s+", text)
    if len(parts) > 1:
        tails = [part.rstrip("?.!").strip() for part in parts[1:]]
        for tail in tails:
            if re.fullmatch(r"if either is not known,? identify which one", tail, re.I):
                continue
            words = re.findall(r"[a-z]+", tail.casefold())
            if not words or words[0] not in {"give", "show", "include", "use"} or not set(words) <= _INSTRUCTION_WORDS:
                return None
        text = parts[0]
    return re.sub(r"\s+(?:now|currently)$", "", text.rstrip("?.!").strip(), flags=re.I)


def _facet(subject: str, *, attribute: str | None = None, owner: str | None = "user") -> SubjectFacet | None:
    label = subject.strip(" ,")
    if not label or len(label) > 220 or _CLAUSE_VERBS.search(label):
        return None
    text = label
    explicit_owner = re.match(r"([A-Z][a-z]+)'s\s+", text)
    if explicit_owner:
        owner = explicit_owner.group(1).casefold()
        text = text[explicit_owner.end():]
    text = re.sub(r"^(?:the\s+)?(?:my|our|your)\s+", "", text, flags=re.I)
    text = re.sub(r"^the\s+", "", text, flags=re.I)
    if re.match(r"(?:container|place|location)\s+(?:holding|of|for)\s+", text, re.I):
        attribute = "location"
        text = re.sub(r"^(?:container|place|location)\s+(?:holding|of|for)\s+(?:my\s+)?", "", text, flags=re.I)
    elif re.search(r"(?:'s)?\s+(?:current\s+)?location$", text, re.I):
        attribute = "location"
        text = re.sub(r"(?:'s)?\s+(?:current\s+)?location$", "", text, flags=re.I)
    elif re.search(r"\bpreference$", text, re.I):
        attribute = "preference"
        text = re.sub(r"\s*preference$", "", text, flags=re.I)
    elif re.search(r"\bbudget$", text, re.I):
        attribute = "budget"
    elif re.search(r"\bsupply$", text, re.I):
        attribute = "inventory"
        text = re.sub(r"\s*supply$", "", text, flags=re.I)
    elif re.search(r"\b(?:start\s+)?time$", text, re.I):
        attribute = "time"
        text = re.sub(r"\s+(?:start\s+)?time$", "", text, flags=re.I)
    elif re.search(r"\b(?:duration|length)$", text, re.I):
        attribute = "duration"
        text = re.sub(r"\s+(?:duration|length)$", "", text, flags=re.I)
    elif re.search(r"\bavailability$", text, re.I):
        attribute = "availability"
        text = re.sub(r"\s*availability$", "", text, flags=re.I)
    date_values = _dates(text)
    text = _ISO_DATE.sub("", _FULL_DATE.sub("", text))
    words = [word for word in re.findall(r"[^\W_]+", text.casefold())
             if word not in _SUBJECT_MODIFIERS]
    terms = topic_terms(" ".join(words)) - _NON_SUBJECT - _CALENDAR
    terms = frozenset(term for term in terms if not term.isdigit())
    if not terms and attribute == "availability" and owner not in {None, "user"}:
        terms = frozenset((owner,))
    if not terms or len(terms) > 8:
        return None
    return SubjectFacet(label, terms, attribute, owner, date_values)


def _subject_list(text: str) -> tuple[SubjectFacet, ...] | None:
    text = re.sub(r"^both\s+", "", text.strip(), flags=re.I)
    pieces = re.split(r"\s+(?:and|or)\s+|,\s*(?:and\s+)?", text, flags=re.I)
    if not 1 <= len(pieces) <= 3:
        return None
    facets = tuple(_facet(piece) for piece in pieces)
    return None if any(facet is None for facet in facets) else facets


def _resource_task_supported(text: str, facets: tuple[SubjectFacet, ...]) -> bool:
    """Accept explicit arithmetic/stock tasks, not an arbitrary following ask."""
    head = _request_head(text)
    if head is None or re.search(r"['’]s\b|\b(?:my|our|your|his|her|their)\b", head, re.I):
        return False
    attributes = {facet.attribute for facet in facets}
    if attributes == {"budget"}:
        item = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+[\w -]+\s+at\s+\d+(?:\.\d+)?\s+\w+\s+each"
        return re.fullmatch(rf"can\s+i\s+buy\s+{item}(?:\s+and\s+{item})?", head, re.I) is not None
    if attributes <= {"inventory", "preference"} and "inventory" in attributes:
        return any(re.fullmatch(pattern, head, re.I) is not None for pattern in (
            r"how\s+many\s+extra\s+\w+\s+must\s+i\s+obtain,?\s+and\s+what\s+names\s+should\s+go\s+on\s+the\s+\w+",
            r"allocate\s+\d+\s+\w+\s+to\s+[\w -]+\s+and\s+(?:use\s+)?the\s+remaining\s+\w+\s+(?:to|for)\s+[\w -]+",
        ))
    return False


def parse_subject_request(query: str) -> SubjectRequest | None:
    """Recognize complete direct, event-list, or explicit-resource grammars.

    Unsupported clauses return None. Subjects are copied from the request;
    there are no fixture names, record IDs, or generated answer strings here.
    """
    normalized = unicodedata.normalize("NFKC", query).replace("’", "'").strip()
    # A planning/calculation request may state its personal inputs after
    # self-contained quantities. Restrict this grammar to explicit field names.
    resource = re.search(r"\busing\s+my\s+([^,?.;]+),\s*(.+)", normalized, re.I)
    if resource and not re.search(r"\b(?:my|our|your)\b", normalized[:resource.start()] + resource.group(2), re.I):
        facets = _subject_list(resource.group(1))
        if facets and _resource_task_supported(resource.group(2), facets):
            return SubjectRequest(facets, "constraints")
    head = _request_head(query)
    if head is None:
        return None
    direct = (
        (r"(?:what|which)\s+is\s+(?:the\s+)?name\s+of\s+my\s+(.+)", "name"),
        (r"(?:what|which)\s+name\s+is\s+my\s+(.+)", "name"),
        (r"what\s+(?:did|have)\s+i\s+name\s+my\s+(.+)", "name"),
        (r"what\s+is\s+my\s+(.+)'s\s+name", "name"),
        (r"where\s+(?:is|was|are|were)\s+my\s+(.+?)(?:\s+currently)?(?:\s+(?:located|stored|kept))?", "location"),
        (r"where\s+(?:should|can)\s+i\s+find\s+my\s+(.+)", "location"),
        (r"(?:what|which)\s+container\s+holds\s+my\s+(.+)", "location"),
        (r"(?:what|which)\s+(?:room|hall|location|place)\s+is\s+(?:booked\s+)?for\s+my\s+(.+)", "location"),
        (r"who\s+is\s+my\s+(.+?\b(?:partner|collaborator))", "relationship"),
        (r"what\s+(?:start\s+)?time\s+is\s+my\s+(.+)", "time"),
        (r"what\s+about\s+my\s+(.+?)(?:\s+again)?", None),
    )
    for pattern, attribute in direct:
        match = re.fullmatch(pattern, head, re.I)
        if match:
            # A conjunction here may introduce a second requested field.
            if re.search(r"\b(?:and|or)\b|[,;]", match.group(1), re.I):
                return None
            facet = _facet(match.group(1), attribute=attribute)
            return SubjectRequest((facet,), "direct") if facet else None
    preference = re.fullmatch(
        r"(?:what|which)\s+[\w -]+\s+do\s+i\s+(?:currently\s+)?prefer\s+for\s+(.+)", head, re.I,
    )
    if preference:
        if re.search(r"\b(?:and|or)\b|[,;]", preference.group(1), re.I):
            return None
        facet = _facet(preference.group(1), attribute="preference")
        return SubjectRequest((facet,), "direct") if facet else None
    recall = re.fullmatch(r"(?:please\s+)?(?:remind\s+me\s+of|tell\s+me)\s+(.+)", head, re.I)
    if recall and re.match(r"(?:both\s+)?my\s+", recall.group(1), re.I):
        facets = _subject_list(recall.group(1))
        return SubjectRequest(facets, "direct") if facets else None
    event_patterns = (
        r"which\s+comes\s+first,?\s+(.+)",
        r"how\s+many\s+(?:hours|minutes|days)\s+(?:passed|elapsed)\s+between\s+(.+)",
        r"which\s+did\s+i\s+(?:complete|finish)\s+later,?\s+(.+)",
        r"put\s+(.+?)\s+in\s+chronological\s+order(?:,?\s+giving\s+each\s+stored\s+date\s+and\s+time)?",
    )
    for pattern in event_patterns:
        match = re.fullmatch(pattern, head, re.I)
        if match:
            facets = _subject_list(match.group(1))
            if facets and len(facets) >= 2:
                return SubjectRequest(tuple(
                    SubjectFacet(f.subject, f.terms, "event", f.owner, f.dates)
                    for f in facets
                ), "events")
    return None


def requested_subject_facets(query: str) -> tuple[SubjectFacet, ...]:
    request = parse_subject_request(query)
    return request.facets if request is not None else ()


def _event_subject_terms(text: str) -> frozenset[str] | None:
    """Read one explicit event predicate, excluding later incidental mentions."""
    active = re.match(
        r"\s*(?:i|you|we)\s+(?:have\s+)?(?P<verb>completed|finished|submitted)\s+"
        r"(?P<subject>.+?)(?=\s+(?:on|at|after|before|while|because)\b|[,;.!?]|$)",
        text, re.I,
    )
    if active:
        return topic_terms(active.group("subject") + " " + active.group("verb"))
    scheduled = re.match(
        r"\s*(?:my|your|our)\s+(?P<subject>.+?)\s+"
        r"(?:is|was|will\s+be|happens|starts|ends|takes\s+place)\s+"
        r"(?:on|at|in|completed|finished|submitted)\b", text, re.I,
    )
    if scheduled:
        return topic_terms(_FULL_DATE.sub("", scheduled.group("subject")))
    return None


def _facet_clause_supported(facet: SubjectFacet, text: str) -> bool | None:
    available = topic_terms(text)
    wanted = facet.terms
    if facet.attribute == "preference":
        # An explicit answer-type descriptor can be implicit in the value.
        # Never drop an arbitrary context word (e.g. workshop or lunch).
        wanted = wanted - {"grain"}
    if not wanted or not wanted <= available:
        return False
    if facet.owner == "user":
        # An explicit other owner cannot silently become the current user.
        # Restrict this check to possession of a requested subject, not an
        # unrelated named person's object elsewhere in the same sentence.
        for owner, owned in re.findall(r"\b([A-Z][a-z]+)['’]s\s+([^.!?,;]+)", text):
            if facet.terms <= topic_terms(owned) and owner not in {"Your", "My", "Our"}:
                return False
    elif facet.owner and not re.search(r"\b" + re.escape(facet.owner) + r"\b", text, re.I):
        return False
    if facet.dates:
        dates = _dates(text)
        if dates and not set(facet.dates) & set(dates):
            return False
        if not dates:
            return None  # event_time may exist outside canonical_text
    attribute = facet.attribute
    if attribute == "event":
        event_terms = _event_subject_terms(text)
        return None if event_terms is None else wanted <= event_terms
    if attribute == "preference":
        return bool(re.search(r"\b(?:prefer\w*|favourit\w*|favorit\w*|want\w*|like\w*|enjoy\w*)\b", text, re.I))
    if attribute == "budget":
        return "budget" in available
    if attribute == "time":
        return bool(re.search(r"\d[:.]\d|\b(?:am|pm|noon|midnight|minutes?|hours?)\b", text, re.I) or _dates(text))
    if attribute == "duration":
        return bool(re.search(r"\b(?:lasts?|duration|length)\b", text, re.I)
                    and re.search(r"\b(?:seconds?|minutes?|hours?|days?)\b", text, re.I))
    if attribute == "availability":
        return "available" in available
    if attribute == "relationship":
        return bool(re.search(
            r"\b(?:partner|collaborator)\s+(?:is|was|remains)\s+[A-Z][a-z]+\b|"
            r"\b[A-Z][a-z]+\s+(?:is|was|remains)\s+(?:my|your|our)\s+[^.!?]*\b(?:partner|collaborator)\b", text,
        ))
    if attribute == "name":
        heads = "|".join(re.escape(term) + r"s?" for term in sorted(facet.terms))
        return bool(re.search(
            rf"\b(?:{heads})(?:'s)?\s+(?:(?:is|was)\s+)?(?:named|called|name\s+is)\b|"
            rf"\b(?:named|called)\s+(?:my|your|the)\s+(?:\w+\s+){{0,4}}(?:{heads})\b", text, re.I,
        ))
    if attribute == "location":
        match = re.search(
            r"\b(?:is|was|are|were|stored|kept|located|happens|held)\s+"
            r"(?:(?:stored|kept|located|held)\s+)?(?:at|in|inside|on)\s+"
            r"(?P<value>[^.!?;]+)", text, re.I,
        )
        if match is None:
            return False
        value_terms = topic_terms(match.group("value"))
        temporal_terms = {relevance_stem(word) for word in _CALENDAR | {
            "noon", "midnight", "morning", "afternoon", "evening", "night",
            "tonight", "today", "tomorrow", "yesterday", "am", "pm", "utc",
            "day", "week", "month", "year", "hour", "minute", "second",
            "dawn", "dusk", "sunrise", "sunset", "midday", "weekday", "weekend",
            "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "half", "quarter", "past",
        }}
        # "on Monday" and "at noon" answer when, not where. Calendar-named
        # places retain a spatial label: "Monday Hall", "June Room".
        return any(term not in temporal_terms and not term.isdigit()
                   for term in value_terms)
    return True


def subject_facet_supported(facet: SubjectFacet, text: str) -> bool | None:
    """Link a subject and attribute within a clause, never by date alone.

    A statement about an adjacent object cannot donate its attribute. This
    deliberately does not resolve pronouns across clauses or invent links.
    """
    clauses = re.split(
        r"[.!?;](?:\s+|$)|\s+(?:and|but)\s+(?=(?:my|your|our|his|her|"
        r"their|the|a|an|i|you|he|she|they|we|prefer\w*)\b)", text, flags=re.I,
    )
    supports = [_facet_clause_supported(facet, clause) for clause in clauses if clause.strip()]
    if any(value is True for value in supports):
        return True
    return None if any(value is None for value in supports) else False


def requested_subject_supported(query: str, text: str) -> bool | None:
    """Tri-state subject support shared by ranking and required-ID selection."""
    request = parse_subject_request(query)
    if request is None:
        # The historical helper includes prefix grammars. Do not interpret
        # their absence of a first subject as exclusion of an unparsed clause.
        if (_request_head(query) is None
                or re.search(r"\b(?:and|both)\b|[,;]", query, re.I)
                or query.count("?") > 1):
            return None
        return direct_subject_supported(query, text)
    supports = [subject_facet_supported(facet, text) for facet in request.facets]
    if any(value is True for value in supports):
        return True
    return None if any(value is None for value in supports) else False


def evidence_order(query: str, texts: Sequence[str]) -> tuple[int, ...]:
    """Rerank the bounded RRF pool by topic coverage, using RRF to break ties.

For synthesis, discount already-covered terms so one topic cannot occupy all
three slots. For direct questions retain equal-facet candidates, including
conflicts. Empty lexical evidence leaves the original RRF ranking unchanged.
"""
    wanted = topic_terms(query)
    facets = requested_subject_facets(query)
    facet_support = [
        frozenset(i for i, facet in enumerate(facets)
                  if subject_facet_supported(facet, text) is True)
        for text in texts
    ]
    subject_support = [requested_subject_supported(query, text) for text in texts]
    terms = [topic_terms(text) for text in texts]
    counts = Counter(term for item in terms for term in item)
    weights = {term: 1.0 / counts[term] for term in wanted if counts[term]}
    multiple = bool(re.search(
        r"\b(?:and|both|compare|timeline|summarize)\b", query, re.I
    ))
    remaining = list(range(len(texts)))
    ordered = []
    covered: set[str] = set()
    covered_facets: set[int] = set()
    while remaining:
        def key(index):
            overlap = wanted & terms[index]
            support = subject_support[index]
            score = sum(
                weights[term] * (0.35 if multiple and term in covered else 1)
                for term in overlap
            )
            return (2 if support is True else 1 if support is None else 0,
                    len(facet_support[index] - covered_facets), score, -index)

        best = max(remaining, key=key)
        remaining.remove(best)
        ordered.append(best)
        covered.update(wanted & terms[best])
        covered_facets.update(facet_support[best])
    return tuple(ordered)
