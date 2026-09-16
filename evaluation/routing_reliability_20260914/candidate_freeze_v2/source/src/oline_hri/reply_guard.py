"""Bounded, route-independent reply checks and conservative history admission.

These English lexical checks detect concrete failures; passing is not a proof
of semantic entailment. They neither grant memory access nor replace source
freshness checks. In particular, callers must provide only currently authorized
facts and must not recycle earlier replies as evidence. Personal turns are
withheld from future generation history even when their facts were supported.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Sequence
import unicodedata

from .memory_evidence import relevance_stem, topic_terms


_WORD = re.compile(r"[\w]+(?:'[\w]+)?", re.UNICODE)
_PERSONAL = re.compile(r"\b(?:my|mine|our|ours|your|yours)\b|\b(?:i|we|you)\s+"
                       r"(?:am|are|was|were|have|had|own|live|work|feel|prefer|like|"
                       r"love|hate|want|need|remember|forgot|met|went|bought|left|put|"
                       r"keep|kept|store|stored|plan|planned|scheduled|completed|"
                       r"submitted|chose|choose|told|said|visited|suffer|saw|lost|"
                       r"take|took|use|used|ate|eat|can\s*not|cannot)\b", re.I)
_PERSONAL_CLAIM = re.compile(
    r"\byour\s+[^.!?;\n]{1,90}?\s+(?:is|are|was|were|has|have|had|"
    r"lies|sits|remains|contains|costs|starts|ends|lasts|begins|takes|"
    r"will\s+be|(?:may|might|could)\s+be)\b|"
    r"\byou(?:'re|'ve|'d)?\s+(?:are|were|have|had|own|live|work|feel|"
    r"prefer|like|love|hate|want|need|remember|forgot|met|went|bought|left|"
    r"put|keep|kept|store|stored|plan|planned|scheduled|completed|submitted|"
    r"chose|choose|told|said|visited|suffer|saw|lost|take|took|use|used|ate|eat)\b|"
    r"\byou(?:'re|'ve)\b|\b(?:is|was|are|were)\s+your\b|"
    r"\byour\s+(?:name|birthday|birthplace|address|appointment|meeting|"
    r"friend|partner|wife|husband|mother|father|sister|brother)\b",
    re.I,
)
_QUESTION_START = re.compile(
    r"^(?:(?:please|so|and|but)\s+)*(?:what|which|who|whose|when|where|why|how|"
    r"can|could|would|should|may|might|will|shall|do|does|did|is|are|was|were|"
    r"have|has|had|tell|remind|remember|explain|suggest|recommend|help|"
    r"write|draft|compose|rewrite|translate|create|make|give|list|find|"
    r"calculate|compare|summarize|describe|show|plan|organize|"
    r"i\s+(?:wonder|wish)|if|suppose|imagine|assuming|whether)\b", re.I,
)
_UNCERTAIN_SOURCE = re.compile(
    r"\b(?:if|whether|maybe|perhaps|possibly|probably|might|could|allegedly|"
    r"apparently|not\s+sure|don't\s+know|do\s+not\s+know|wonder)\b", re.I,
)
_NO_KNOWLEDGE = re.compile(
    r"\b(?:i\s+(?:do\s+not|don't|cannot|can't)\s+(?:know|recall|remember|"
    r"confirm|verify|tell)|i\s+(?:do\s+not|don't)\s+have\s+(?:a\s+)?"
    r"(?:verified|reliable|enough|that|this|the)|"
    r"i(?:'m|\s+am)\s+(?:not\s+sure|uncertain)|"
    r"(?:i\s+)?(?:need|would\s+need)\s+(?:you\s+to|more\s+information)|"
    r"(?:do\s+not|don't)\s+know\s+(?:your|where|when|who|what))\b", re.I,
)
_ADVICE = re.compile(
    r"^(?:(?:you\s+)?(?:can|could|should|may|might|must|need\s+to)|"
    r"please|try|consider|avoid|check|ask|take|drink|rest|contact|seek|call|"
    r"use|start|stop|make|keep|write|list|choose|set|break|turn|open|close|"
    r"save|restart|install|reinstall|look|put|move|compare|read|give|tell|"
    r"let|remember\s+to|if|when|for\s+example|for\s+instance)\b", re.I,
)
_DRAFT_REQUEST = re.compile(
    r"\b(?:write|draft|compose|rewrite|translate|make\s+up|create)\b.{0,100}"
    r"\b(?:story|poem|letter|note|email|message|dialogue|script|scene|speech|"
    r"fiction|fictional|first.person|sentence|paragraph|text|fable|song|"
    r"apology|greeting|welcome)\b", re.I,
)
_WORDING_REQUEST = re.compile(
    r"\b(?:give|suggest|show|write|offer)\b.{0,60}\b(?:ways?|wording|phrases?|sentences?)\s+"
    r"(?:to|for)\s+(?:say|ask|thank|apologize|apologise|invite|decline|greet|congratulate)\b",
    re.I,
)
_FOLLOWUP = re.compile(
    r"\b(?:again|repeat|shorter|longer|simpler|rephrase|rewrite|that|those|"
    r"above|previous|continue|expand|more\s+detail)\b", re.I,
)
_ARTIFACT_EDIT = re.compile(
    r"^(?:please\s+)?(?:make\s+(?:it|that|the\s+(?:story|draft|text|opening|ending|greeting|apology|welcome)|"
    r"(?:the\s+)?(?:first|second|third|fourth|last|\d+(?:st|nd|rd|th))\s+"
    r"(?:one|draft|option|version))\s+(?:sound\s+)?"
    r"(?:shorter|longer|simpler|funnier|warmer|clearer|"
    r"(?:more|less)\s+(?:direct|formal|casual|friendly|warm|concise|detailed|"
    r"polite|personal|technical|dramatic|welcoming))|shorten|lengthen|rewrite|rephrase|"
    r"expand|continue|change\s+(?:the\s+)?(?:ending|opening|tone))\b", re.I,
)
_GENERAL_HOW_TO = re.compile(
    r"^how\s+(?:can|could|do|should)\s+i\s+(?:learn|write|solve|calculate|"
    r"install|use|debug|understand|explain|create|implement|practice|study)\b", re.I,
)
_RELATIONSHIP_WORD = re.compile(
    r"\b(?:acquaintance|aunt|brother|child|client|colleague|cousin|coworker|"
    r"daughter|father|friend|husband|manager|mentor|mother|neighbor|parent|"
    r"partner|relative|sibling|sister|son|spouse|teammate|uncle|wife)\b", re.I,
)
_ROBOT_ACTION = re.compile(
    r"^(?:(?:and|then|now)\s+)*i(?:'ll|\s+(?:will|shall|can|did)|"
    r"\s+have(?:\s+already)?|\s+am(?:\s+(?:now|currently))?)?\s+"
    r"(?:already\s+|now\s+)?"
    r"(?P<verb>cook|cooked|cooking|bake|baked|baking|boil|boiled|boiling|"
    r"bring|brought|bringing|move|moved|moving|carry|carried|carrying|"
    r"lift|lifted|lifting|fetch|fetched|fetching|place|placed|placing|"
    r"put|putting|prepare|prepared|preparing|make|made|making)\b"
    r"(?P<object>.*)$", re.I,
)
_PHYSICAL_OBJECT = re.compile(
    r"\b(?:chair|chairs|table|tables|desk|desks|box|boxes|cup|cups|mug|mugs|"
    r"bowl|bowls|plate|plates|bottle|bottles|glass|glasses|water|tea|coffee|"
    r"book|books|bag|bags|key|keys|camera|telescope|projector|plant|plants|"
    r"cushion|cushions|pillow|pillows|sofa|couch|bed|door|window|clothes|"
    r"laundry|package|packages|parcel|parcels|furniture|objects?|dinner|"
    r"lunch|breakfast|meal|meals|food|rice|peas|onion|soup|sandwich|pasta|"
    r"salad|bread|cake|cookies|vegetables)\b", re.I,
)
_DIGITAL_ARTIFACT = re.compile(
    r"\b(?:answer|explanation|summary|draft|note|letter|email|message|text|"
    r"paragraph|sentence|word|example|calculation|code|function|file|folder|"
    r"document|outline|plan|checklist|instructions|recipe|list|report|"
    r"presentation|argument|point|idea|topic|discussion|conversation)\b", re.I,
)
_FUNCTION_WORDS = frozenset(
    "a an the i me my mine we us our ours you your yours user's user "
    "am is are was were be been being have has had do does did "
    "it its this that these those still currently now actually "
    "as at to of on in inside into within from with for by and also "
    "said told mentioned say tell mention earlier previously "
    "sorry hear sounds sound seem seems feeling experiencing".split()
)
_ALIASES = {
    "located": "location", "stored": "location", "stowed": "location",
    "kept": "location", "sits": "location", "lies": "location",
    "reside": "live", "resides": "live", "residing": "live",
    "cupboard": "cabinet", "cupboards": "cabinet",
    "named": "name", "called": "name",
    "chose": "choose",
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12",
}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).replace("’", "'")
    for before, after in (("I'm", "I am"), ("you're", "you are"),
                          ("I've", "I have"), ("you've", "you have"),
                          ("don't", "do not"), ("isn't", "is not"),
                          ("aren't", "are not"), ("wasn't", "was not")):
        value = re.sub(r"\b" + re.escape(before) + r"\b", after, value, flags=re.I)
    return value.strip()


def _clauses(text: str) -> tuple[str, ...]:
    # Preserve digits in times/decimals; never join witnesses across records.
    return tuple(part.strip(' \t\r\n"') for part in re.split(
        r"[!?;\n]+|(?<!\d)\.(?!\d)|,|\b(?:but|however|although|yet|because|since)\s+|"
        r"\band\s+(?=(?:your|my|you|i|our)\b)",
        _normalize(text), flags=re.I,
    ) if part.strip(' \t\r\n"'))


def _assertions(text: str) -> tuple[str, ...]:
    result: list[str] = []
    # A question's subordinate predicate is not evidence, even if a comma
    # separates it from the question head. Process whole sentences first.
    for sentence in re.split(r"(?<=[.!?])\s+|[;\n]", _normalize(text)):
        # Do not promote a first-person quotation by another speaker into a
        # disclosure by the current human when splitting comma clauses.
        if re.search(r"\b(?:said|says|told|wrote|writes|claims|claimed)\b"
                     r"[^.!?]{0,70}[,:\"“]", sentence, re.I):
            continue
        if sentence.rstrip().endswith("?"):
            # A leading independently asserted clause remains usable in
            # "I have a headache, what should I do?".
            prefix = re.split(r",\s*(?=(?:what|which|who|when|where|why|how|"
                              r"can|could|would|should|do|does|did)\b)",
                              sentence, maxsplit=1, flags=re.I)
            if len(prefix) == 1:
                continue
            sentence = prefix[0]
        if _QUESTION_START.search(sentence.strip()) or _UNCERTAIN_SOURCE.search(sentence):
            continue
        for clause in _clauses(sentence):
            clause = re.sub(r"^(?:since|because)\s+", "", clause, flags=re.I)
            if not _QUESTION_START.search(clause) and not _UNCERTAIN_SOURCE.search(clause):
                result.append(clause)
    return tuple(result)


def _content(text: str) -> frozenset[str]:
    tokens = []
    for word in _WORD.findall(_normalize(text).casefold()):
        word = _ALIASES.get(word, word)
        if word not in _FUNCTION_WORDS:
            tokens.append(relevance_stem(word))
    # "is in" and "is stored in" have the same lexical location value.
    return frozenset(tokens) - {"location"}


def _location_facet(text: str) -> tuple[str, frozenset[str]] | None:
    """Bind a simple location preposition to its own first object phrase."""
    spatial = r"in\s+front\s+of|next\s+to|in|inside|within|outside|beside|near|under|beneath|above|on|at|behind"
    match = re.search(rf"\b({spatial})\s+(.+)", text, re.I)
    if match is None:
        return None
    relation = match.group(1).casefold()
    relation = {"inside": "in", "within": "in", "beneath": "under"}.get(relation, relation)
    target = re.split(rf"\b(?:{spatial}|and|but|which|that)\b", match.group(2),
                      maxsplit=1, flags=re.I)[0]
    return relation, _content(target)


def _supported(claim: str, sources: Sequence[str]) -> bool:
    terms = _content(claim)
    if not terms:
        return False
    negative = bool(re.search(r"\b(?:not|never|no)\b", claim, re.I))
    past = bool(re.search(r"\b(?:was|were|used\s+to|formerly)\b", claim, re.I))
    for source in sources:
        # A fact about somebody else's camera cannot authorize "your camera".
        # Likewise an owned book mentioning a friend's name is no witness for
        # that person's relationship to the user.
        if not _PERSONAL.search(_normalize(source)):
            continue
        owned = _owned_subject_terms(claim)
        if owned and not owned.issubset(_owned_subject_terms(source)):
            continue
        location = _location_facet(claim)
        if location:
            source_location = _location_facet(source)
            if (source_location is None or location[0] != source_location[0]
                    or not location[1].issubset(source_location[1])):
                continue
        if negative != bool(re.search(r"\b(?:not|never|no)\b", source, re.I)):
            continue
        if past != bool(re.search(r"\b(?:was|were|used\s+to|formerly)\b", source, re.I)):
            continue
        if terms.issubset(_content(source)):
            return True
    return False


def is_drafting_request(user_text: str) -> bool:
    """Recognize explicit requests for a written artifact, not personal recall."""
    return bool(_DRAFT_REQUEST.search(user_text) or _WORDING_REQUEST.search(user_text))


def is_drafting_followup(user_text: str) -> bool:
    """Recognize an artifact edit which still requires prior drafting context."""
    return bool(_ARTIFACT_EDIT.search(user_text))


def _owned_subject_terms(text: str) -> frozenset[str]:
    result = set()
    for match in re.finditer(r"\b(?:my|our|your)\s+([\w' -]{1,70})", text, re.I):
        phrase = re.split(r"\b(?:is|are|was|were|has|have|had|can|could|will|"
                          r"may|might|if|and|but|which|that|on|at|in|with|to|for|"
                          r"contains|starts|ends|lies|sits|remains|mentions|"
                          r"describes|discusses|references|concerns)\b", match.group(1),
                          maxsplit=1, flags=re.I)[0]
        # A postposed proper name is checked by _content against the same
        # witness; it is a value rather than the owned relationship's head.
        phrase = " ".join(word for word in phrase.split() if not word[:1].isupper())
        result.update(topic_terms(phrase))
    return frozenset(result)


def current_assertions(user_text: str) -> tuple[str, ...]:
    """Extract bounded current assertions without promoting question premises.

    This does not establish truth or memory consent; it only identifies what
    the human supplied for this turn. Unrecognized/uncertain wording is omitted.
    """
    return _assertions(user_text)


def has_personal_record_question(user_text: str) -> bool:
    """Recognize bounded recall grammar, not topics or evidence authority.

    A supplied current assertion may answer such a question. Callers must
    check that separately; this signal alone never authorizes a value.
    """
    if is_drafting_request(user_text):
        return False
    for sentence in re.split(r"(?<=[.!?])\s+|[;\n]", _normalize(user_text)):
        if not re.match(r"^(?:what|which|where|when|who|whose)\b", sentence, re.I):
            continue
        past_event = re.search(r"\b(?:did|have|had)\s+i\b", sentence, re.I)
        past_relative = (re.search(r"\b(?:was|were)\b", sentence, re.I)
                         and re.search(r"\bi\s+[a-z]+ed\b", sentence, re.I))
        relationship = re.search(r"\b(?:in\s+relation\s+to|relationship\s+with)\s+me\b",
                                 sentence, re.I)
        revised_record = (
            re.search(r"\b(?:current|saved|recorded|corrected|updated)\b", sentence, re.I)
            and re.search(r"\b(?:after|following)\s+(?:(?:the|a|that|my|your)\s+)?"
                          r"(?:correction|update)\b", sentence, re.I)
        )
        if past_event or past_relative or relationship or revised_record:
            return True
    return False


def _robot_physical_action_claim(user_text: str, speech: str) -> bool:
    """Catch bounded robot self-claims in this text-output deployment.

    These are action claims, not human facts: personal evidence cannot
    authorize them. Object checks keep digital preparation/movement distinct
    from physical manipulation; this finite check is not a capability proof.
    """
    physical_context = bool(_PHYSICAL_OBJECT.search(user_text))
    for clause in _clauses(speech):
        match = _ROBOT_ACTION.match(clause)
        if match is None:
            continue
        target = re.split(r"\b(?:and|then|for|with|while|about)\b",
                          match.group("object"), maxsplit=1, flags=re.I)[0]
        # Preparing a recipe or moving a paragraph remains a textual task,
        # including when the request discusses food or physical objects.
        if _DIGITAL_ARTIFACT.search(target):
            continue
        verb = match.group("verb").casefold()
        if verb in {"cook", "cooked", "cooking", "bake", "baked", "baking",
                    "boil", "boiled", "boiling"}:
            if not re.match(r"\s+up\b", target, re.I):
                return True
        elif _PHYSICAL_OBJECT.search(target):
            return True
        elif physical_context and re.fullmatch(
                r"\s*(?:it|that|this|them|those|these)(?:\s+(?:now|already|"
                r"here|there|over|over\s+here|over\s+there|for\s+you))*\s*",
                target, re.I):
            return True
    return False


def _personal_subjects(user_text: str) -> frozenset[str]:
    subjects = set()
    for match in re.finditer(r"\b(?:my|our)\s+([\w' -]{1,70})", user_text, re.I):
        phrase = re.split(r"\b(?:is|are|was|were|has|have|had|if|and|but|which|"
                          r"that|on|at|in|with|to|for)\b", match.group(1),
                          maxsplit=1, flags=re.I)[0]
        subjects.update(topic_terms(phrase))
    return frozenset(subjects)


def _elliptical_recall_clause(clause: str, *, allow_bare_value: bool = True) -> bool:
    """A value-shaped answer, rather than every sentence in a mixed reply."""
    words = _WORD.findall(clause)
    return bool(
        re.match(r"^(?:in|inside|at|on|within|near|beside|under|behind)\b|"
                 r"^(?:it|they|that|this)\s+(?:is|are|was|were)\b", clause, re.I)
        or allow_bare_value and (len(words) <= 2
        or (len(words) <= 5 and re.match(r"^(?:the|a|an)\b", clause, re.I)
            and not re.search(r"\b(?:is|are|was|were|has|have|can|could|will)\b", clause, re.I))
        or (len(words) <= 3 and all(word[:1].isupper() or word.isdigit() for word in words)))
    )


def _record_value_clause(clause: str) -> bool:
    return bool(re.match(
        r"^(?:it|they|(?:the|this|that)\s+(?:[\w'-]+\s+){1,5})"
        r"\s*(?:(?:is|are|was|were)\s+(?:called|named|chosen|selected|scheduled)\b|"
        r"(?:starts?|begins?|ends?|is|are|was|were)\s+(?:at|on|from|until)\s+\d)",
        clause, re.I,
    ))


def _bound_record_sources(user_text: str, claim: str, sources: Sequence[str]) -> tuple[str, ...]:
    """Bind an omitted answer subject to the same source as its value.

    This is deliberately a small grammar: unsupported paraphrases can be
    withheld, and no word overlap across separate witnesses grants support.
    """
    if not (_elliptical_recall_clause(claim) or _record_value_clause(claim)):
        return tuple(sources)
    questions = [s for s in re.split(r"(?<=[.!?])\s+|[;\n]", _normalize(user_text))
                 if re.match(r"^(?:what|which|where|when|who|whose)\b", s, re.I)]
    result = []
    for source in sources:
        bound = True
        for question in questions:
            owned = _personal_subjects(question)
            if owned and not owned.issubset(_owned_subject_terms(source)):
                bound = False
                break
            person = re.search(r"\bwho\s+(?:is|was)\s+(.+?)\s+in\s+relation\s+to\s+me\b",
                               question, re.I)
            if person:
                name = re.escape(person.group(1).strip())
                value = re.escape(re.sub(r"^(?:your|my|our|the|a|an)\s+", "", claim, flags=re.I))
                if not re.search(
                    rf"\b{name}\s+(?:is|was)\s+(?:my|our|your)\s+{value}\b|"
                    rf"\b(?:my|our|your)\s+{value}\s+(?:(?:is|was)\s+)?{name}\b",
                    source, re.I,
                ):
                    bound = False
                    break
            action = re.search(r"\b(?:did|have|had)\s+i\s+([a-z]+)\b", question, re.I)
            if action:
                predicates = re.findall(r"\b(?:i|you)\s+(?:(?:have|had)\s+)?([a-z]+)\b",
                                        source, re.I)
                if not any(_content(verb) == _content(action.group(1)) for verb in predicates):
                    bound = False
                    break
                target = re.search(r"\bfor\s+(?:the\s+)?(.+?)[?]?$", question, re.I)
                source_target = re.search(r"\bfor\s+(.+)$", source, re.I)
                if (target and source_target
                        and not _content(target.group(1)).issubset(_content(source_target.group(1)))):
                    bound = False
                    break
            anchor = re.search(
                r"\b(?:for|of)\s+(?:the|my|our)\s+(.+?)\s+(?:after|following)\b|"
                r"\b(?:the|my|our)\s+(.+?)\s+i\s+[a-z]+ed\b", question, re.I,
            )
            if anchor:
                terms = _content(anchor.group(1) or anchor.group(2))
                if not terms.issubset(_content(source)):
                    bound = False
                    break
        if bound:
            result.append(source)
    return tuple(result)


def _reply_clauses(speech: str):
    """Keep comma-list examples attached to their general sentence.

    Bare nouns after an explicit illustration marker are examples, not
    additional elliptical answers to a personal slot. Location/owner claims
    are still checked, and the exception ends at the sentence boundary.
    """
    for sentence in re.split(r"[!?;\n]+|(?<!\d)\.(?!\d)", _normalize(speech)):
        general_list = False
        personal_context = False
        for clause in _clauses(sentence):
            if _PERSONAL.search(clause):
                personal_context = True
                general_list = False
            elif not personal_context and re.search(
                r"\b(?:such\s+as|including|for\s+example|for\s+instance)\b", clause, re.I,
            ):
                general_list = True
            yield clause, general_list


def _personal_fragments(user_text: str, speech: str) -> tuple[str, ...]:
    subjects = _personal_subjects(user_text)
    record_question = has_personal_record_question(user_text)
    direct_recall = record_question or bool(subjects and re.search(
        r"\b(?:where|when|who|whose|what\s+(?:is|was|are|were|colou?r|name)|"
        r"which\s+(?:is|was|room|day)|remind|recall|remember)\b", user_text, re.I,
    ))
    result = []
    for clause, general_list in _reply_clauses(speech):
        if _NO_KNOWLEDGE.search(clause) or _QUESTION_START.search(clause):
            continue
        # Modal suggestions and imperatives don't assert a personal fact.
        if _ADVICE.search(clause):
            continue
        personal = _PERSONAL_CLAIM.search(clause)
        if personal:
            # Omit an empathy preamble while retaining reversed relationship
            # claims ("Noor is your friend") and their named value.
            start = personal.start()
            if re.match(r"you\b", clause[start:], re.I) and start > 0:
                clause = clause[start:]
            result.append(clause)
        elif subjects.intersection(topic_terms(clause)) and re.search(
            r"\b(?:is|are|was|were|has|contains|lies|sits|stored|located|"
            r"stowed|kept|starts|ends|scheduled)\b", clause, re.I,
        ):
            result.append(clause)
        elif direct_recall and _elliptical_recall_clause(clause, allow_bare_value=not general_list):
            # Elliptical answers such as "Noor" or "In the amber cabinet"
            # are still assertions when answering an explicit personal slot.
            result.append(clause)
        elif record_question and _record_value_clause(clause):
            # Named values and times can omit both owner and request noun.
            # Their authority still comes from a single current fact.
            result.append(clause)
    return tuple(result)


def _repetitive(text: str) -> bool:
    sentences = [" ".join(_WORD.findall(part.casefold())) for part in _clauses(text)]
    counts = Counter(part for part in sentences if len(part.split()) >= 4)
    if any(count >= 2 for count in counts.values()):
        return True
    words = _WORD.findall(text.casefold())
    # Detect loops even without punctuation; tolerate ordinary repeated words.
    if len(words) >= 18:
        counts = Counter(tuple(words[i:i + 5]) for i in range(len(words) - 4))
        return any(count >= 3 for count in counts.values())
    return False


def _promise_only(user_text: str, text: str) -> bool:
    """Recognize replies made entirely of conversational scaffolding.

    Request echoes with only generic qualifiers, optional-context conditions
    and abstract promises are not a delivered answer. Any concrete payload
    keeps this bounded English check from declaring the reply empty; the
    independent reviewer remains responsible for its actual usefulness.
    """
    clauses = _clauses(text)
    if not clauses:
        return False
    request_clauses = _clauses(user_text)
    # A request for a question or missing requirements can be fulfilled by
    # asking for those details. Ordinary necessary clarifications with a
    # concrete referent also fall outside the abstract payload grammar below.
    if any(re.search(
        r"^(?:please\s+)?(?:(?:(?:can|could|would)\s+you|"
        r"i\s+(?:want|need)\s+you\s+to)\s+)?(?:ask|clarify)\b|"
        r"\b(?:what|which)\s+(?:(?:kind|type|sort)\s+of\s+)?"
        r"(?:details|information|context)\b|"
        r"\bwhat\s+(?:should|can|do)\s+i\s+(?:tell|share|provide)\b",
        clause, re.I,
    ) for clause in request_clauses):
        return False
    words = lambda value: tuple(_WORD.findall(value.casefold()))
    echoes = {words(re.sub(r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
                           r"(?:please\s+)?", "", clause, flags=re.I))
              for clause in request_clauses
              if _QUESTION_START.search(clause)}
    abstract_words = _FUNCTION_WORDS | frozenset(
        "can could will would shall may here ready happy glad able only yes "
        "help helps assist assistance tailor tailored customize personalized "
        "personalize suggest suggestions suggestion recommend recommendation "
        "recommendations offer provide give explain explanation explanations "
        "answer answers guide advice ideas idea information context detail "
        "details example examples option options request task question questions "
        "need needs want wants goal goals preference preferences interest "
        "interests requirement requirements constraints specifics level general "
        "specific personal more further any some them what which how else "
        "know ask hope feel free please if once then otherwise accordingly "
        "align aligns aligned suit suits suited suitable match matches matching "
        "based according depending relevant appropriate way ways manner".split()
    )

    def abstract_payload(value: str) -> bool:
        return all(word in abstract_words for word in words(value))

    def request_echo(value: str) -> bool:
        tokens = words(value)
        if tokens in echoes:
            return True
        # Preserve the complete request clause as an anchor. Only a suffix
        # made entirely of generic scaffolding counts as an empty restatement;
        # a concrete example or instruction makes the whole reply nonempty.
        return any(len(echo) >= 2 and tokens[:len(echo)] == echo
                   and all(word in abstract_words for word in tokens[len(echo):])
                   for echo in echoes)

    def scaffolding(clause: str) -> bool:
        clause = re.sub(r"^(?:(?:and|otherwise|then|please)\s+)+", "", clause, flags=re.I)
        if request_echo(clause):
            return True
        if re.fullmatch(r"sure|certainly|of\s+course|okay|ok|absolutely|hello|hi|yes|"
                        r"otherwise|then|how\s+can\s+i\s+help", clause, re.I):
            return True
        condition = re.match(r"^if\s+you\s+(?:have|want|need|would\s+like)\b(.*)$", clause, re.I)
        if condition and abstract_payload(condition.group(1)):
            return True
        solicit = re.match(
            r"^(?:(?:can|could|would)\s+you\s+)?(?:share|provide|give\s+me|"
            r"tell\s+me|let\s+me\s+know|feel\s+free\s+to\s+ask)\b(.*)$", clause, re.I,
        )
        if solicit and abstract_payload(solicit.group(1)):
            return True
        promise = re.match(
            r"^(?:i|we)(?:'ll|'d|\s+(?:can|could|will|would|am|are))\s+(.+)$", clause, re.I,
        )
        if promise:
            payload = re.sub(r"^(?:be\s+)?(?:here|happy|glad|ready|able)\s+to\s+", "",
                             promise.group(1), flags=re.I)
            return request_echo(payload) or abstract_payload(payload)
        return bool(re.match(r"^i\s+hope\b", clause, re.I) and abstract_payload(clause))

    return all(scaffolding(clause) for clause in clauses)


def _blanket_refusal_with_advice(text: str) -> bool:
    """Flag an unqualified inability claim followed by offered assistance.

    This requests a quality retry, not a judgment about permitted content.
    Specific limitations (diagnosis, physical actions, unavailable facts) and
    standalone refusals stay with the independent answer reviewer.
    """
    clauses = _clauses(text)
    if not clauses:
        return False
    denial = re.search(
        r"\bi\s+(?:cannot|can't|can\s+not|am\s+unable\s+to)\s+help"
        r"(?:\s+you)?\s+with\s+(?:your|that|this|the\s+(?:question|request|task))\b",
        clauses[0], re.I,
    )
    return bool(denial and any(_ADVICE.search(clause) for clause in clauses[1:]))


def inspect_reply(
    user_text: str,
    speech: str,
    *,
    authorized_facts: Sequence[str] = (),
    prior_replies: Sequence[str] = (),
    drafting: bool = False,
) -> tuple[str, ...]:
    """Return stable issue codes; never alter text or authorize its evidence.

    Current user assertions are automatically eligible evidence. Question
    predicates and hypothetical clauses are not. ``authorized_facts`` must
    contain only freshly verified, permitted records (not old chat history).
    Lexical paraphrases outside the bounded grammar may need a model review.
    """
    if not speech.strip():
        return ("empty_reply",)
    issues = []
    # The flag is a hint, not an escape hatch for ordinary personal recall.
    draft = is_drafting_request(user_text) or bool(drafting and _ARTIFACT_EDIT.search(user_text))
    if _repetitive(speech) and not draft:
        issues.append("repetition")
    acknowledgement = bool(
        current_assertions(user_text)
        and re.fullmatch(r"\s*(?:okay|ok|understood|got\s+it|thanks|thank\s+you|sure)[.!\s]*",
                         speech, re.I)
        and not re.search(r"[?]|\b(?:what|where|when|which|who|how|why|help|"
                          r"suggest|recommend|tell|explain)\b", user_text, re.I)
    )
    if not draft and _promise_only(user_text, speech) and not acknowledgement:
        issues.append("promise_only")
    if not draft and _blanket_refusal_with_advice(speech):
        issues.append("unhelpful_refusal")
    if not draft and _robot_physical_action_claim(user_text, speech):
        issues.append("physical_action_claim")
    normalized = " ".join(_WORD.findall(speech.casefold()))
    if (len(normalized.split()) >= 8 and not _FOLLOWUP.search(user_text)
            and not topic_terms(user_text).intersection(topic_terms(speech))
            and any(normalized == " ".join(_WORD.findall(old.casefold()))
                    for old in prior_replies)):
        issues.append("copied_reply")
    # First-person draft prose is not a factual claim about the human. Do not
    # use a writing request to excuse second-person factual commentary.
    sources = tuple(clause for text in (user_text, *authorized_facts)
                    for clause in _assertions(text))
    bounded_wording = draft and _bounded_wording_artifact(
        user_text, speech, continuation=drafting,
    )
    if not bounded_wording and any(not _supported(claim, _bound_record_sources(user_text, claim, sources))
                                  for claim in _personal_fragments(user_text, speech)):
        issues.append("unsupported_personal_claim")
    return tuple(issues)


def _bounded_wording_artifact(user: str, answer: str, *, continuation: bool) -> bool:
    """Admit generic wording, never a container for remembered real values.

    This narrow exception permits generic pronouns in social wording and its
    edits. It does not extend admission to ordinary personal notes, supplied
    disclosures, named people, dates, locations, or preference statements.
    """
    if not (_WORDING_REQUEST.search(user) or continuation and _ARTIFACT_EDIT.search(user)):
        return False
    if current_assertions(user):
        return False
    # Numeric list counts/labels are formatting, rather than personal values.
    request = re.sub(r"\b\d+\s+(?:(?:short|brief)\s+)?(?:ways?|phrases?|sentences?|options?)\b",
                     "", user, flags=re.I)
    artifact = re.sub(r"(?:^|(?<=[.!?])\s+)\d+[.)]\s*", "", answer)
    combined = request + "\n" + artifact
    if re.search(
        r"\d|\b(?:remember|recall|remind|remembered|earlier|previously|told|"
        r"yesterday|today|tomorrow|tonight|morning|evening|monday|tuesday|"
        r"wednesday|thursday|friday|saturday|sunday|january|february|march|"
        r"april|june|july|august|september|october|november|december|"
        r"prefer|prefers|preferred|preference|preferences|favorite|favourite|enjoy)\b",
        combined, re.I,
    ):
        return False
    # Unknown capitalized tokens are conservatively withheld as possible
    # names. Familiar sentence openings are allowed, not arbitrary names.
    openings = {"give", "suggest", "show", "write", "offer", "make", "please", "can", "could",
                "would", "i", "we", "you", "your", "thanks", "thank", "hey", "hi", "hello",
                "dear", "it", "that", "this", "what", "how", "really"}
    if any(token[:1].isupper() and token.casefold() not in openings
           for token in _WORD.findall(combined)):
        return False
    # "in keeping ..." is grammatical wording; a spatial qualifier is not.
    if re.search(r"\b(?:at|inside|outside|near|behind|beside|under|from)\s+\w|"
                 r"\bin\s+(?!(?:\w+ing|advance)\b)\w|"
                 r"\bi\s+(?:live|work|own|have|had|bought|left|put|stored|"
                 r"met|visited|went|like|love)\b", combined, re.I):
        return False
    if re.search(r"\b(?:my|our)\s+(?:(?!\b(?:i|we|you|while|when|because|"
                 r"since|if|that)\b)[\w'-]+\s+){1,6}(?:is|are|was|were|has|have|had)\b",
                 answer, re.I):
        return False
    return not any(_PERSONAL_CLAIM.search(clause) for clause in _clauses(answer))


def safe_history_pair(user_text: str, speech: str, *, drafting: bool = False) -> bool:
    """Admit only general task context and explicitly requested draft artifacts.

    Personal questions, disclosures and assistant claims are excluded even
    when a route called them general or their evidence was valid at the time.
    This prevents an earlier authorized value surviving deletion in history.
    Bare follow-ups with no personal wording are safe only if the caller also
    knows they do not continue a withheld personal turn.
    """
    user = _normalize(user_text)
    answer = _normalize(speech)
    if not user or not answer:
        return False
    # Admission is based on the form of a general task, not an enumeration of
    # personal verbs. This withholds "I enjoy ...", "My hobby ..." and named
    # third-person disclosures just as it withholds "I live ...".
    draft = is_drafting_request(user) or bool(drafting and _ARTIFACT_EDIT.search(user))
    if not (draft or _QUESTION_START.search(user) or user.endswith("?")):
        return False
    if draft and re.search(r"\b(?:remember|recall|remind|remembered|earlier|previously|told)\b", user, re.I):
        return False
    if (draft and not re.search(r"\b(?:fiction|fictional|imaginary)\b", user, re.I)
            and re.search(r"\b(?:to|for|from|about)\s+[A-Z][a-z]+\b", user)):
        return False
    ordinal_edit = bool(drafting and _ARTIFACT_EDIT.search(user) and re.search(
        r"\b(?:first|second|third|fourth|last|\d+(?:st|nd|rd|th))\s+(?:one|draft|option|version)\b", user, re.I,
    ))
    if _WORDING_REQUEST.search(user) or ordinal_edit:
        return _bounded_wording_artifact(user, answer, continuation=drafting)
    if re.search(r"\b(?:my|mine|our|ours)\b", user, re.I):
        return False
    if re.search(r"\b(?:i|we)\b", user, re.I) and not _GENERAL_HOW_TO.search(user):
        return False
    if _PERSONAL.search(user):
        return False
    if draft:
        # Addressee pronouns in a greeting/apology are wording, while an
        # actual second-person factual claim remains inadmissible.
        return not _personal_fragments(user, answer)
    if not draft:
        # A named person's whereabouts/past is personal even without my/your.
        # Capitalized public topics in these grammars may also be withheld;
        # conservative history admission is not an entity identity service.
        names = [name for name in re.findall(r"\b[A-Z][a-z]+\b", user)
                 if name.casefold() not in {
                     "what", "where", "when", "who", "whose", "which", "why", "how",
                     "can", "could", "would", "should", "do", "does", "did", "is", "are",
                     "tell", "remind", "explain", "please", "give", "suggest", "show",
                     "summarize", "make", "write", "draft", "no", "yes", "if", "the",
                 }]
        if names and (re.search(r"\b(?:where|when|who|whose|why|does|did)\b", user, re.I)
                      or re.search(r"\b[A-Z][a-z]+['’]s\b", user)):
            return False
    if re.search(r"\byour(?:s)?\b", answer, re.I):
        return False
    if _RELATIONSHIP_WORD.search(answer) and re.search(r"\b[A-Z][a-z]+\b", answer):
        return False
    if not draft and re.search(r"\b(?:i|me|my|mine|we|us|our|ours)\b", answer, re.I):
        return False
    for clause in _clauses(answer):
        if re.search(r"\byou\b", clause, re.I) and not (
            _ADVICE.search(clause) or _QUESTION_START.search(clause)
        ):
            return False
    return True
