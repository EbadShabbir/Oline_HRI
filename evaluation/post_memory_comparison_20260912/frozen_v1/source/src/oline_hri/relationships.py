"""Conservative coverage checks for explicit named user relationships.

This is a bounded English heuristic, not a general semantic parser. It checks
positive copular, appositional, and coordinated statements with familiar role
nouns. Unsupported source wording creates no additional requirement. Once a
source relationship is recognized, its person, role, and descriptive qualifiers
must occur together in an equivalent supported response phrase.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_ROLES = frozenset(
    "acquaintance aunt brother child client colleague cousin coworker daughter "
    "father friend husband manager mentor mother neighbor parent partner "
    "relative sibling sister son spouse teammate uncle wife".split()
)
_IRREGULAR_ROLES = {"children": "child", "wives": "wife"}
_STOP_MODIFIERS = frozenset(
    "a an and are as at be been being but by can could does for from had has "
    "have he her hers him his i in is it its may me might my no not of on or "
    "our ours shall she should that the their theirs them they this those to "
    "us was we were what when where which while who will with would you your "
    "yours also then only never maybe perhaps possible potential alleged "
    "purported uncertain unconfirmed unknown reportedly apparently "
    "ask asks meet meets invite invites help helps review reviews discuss "
    "discusses join joins work works coordinate coordinates".split()
)
_NON_NAMES = frozenset(
    "a an and as ask based coordinate current first for from he her his i "
    "if invite it maybe meet no not perhaps plan possibly probably second "
    "she step that the their third this user we whether with yes you your "
    "allegedly apparently supposedly presumably".split()
)
_SOURCE_POSSESSIVE = r"(?:your|my|(?:the\s+)?user's)"
_SOURCE_HUMAN = r"(?:you|I|(?:the\s+)?user)"
_NAME_PATTERN = re.compile(
    r"(?<![\w'])[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?"
    r"(?:[ \t]+[A-Z][a-z]+){0,2}(?![\w'])"
)
_WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_UNCERTAIN_PREFIX = re.compile(
    r"\b(?:if|whether|maybe|perhaps|not|never|allegedly|apparently|"
    r"possibly|probably|supposedly|presumably|"
    r"(?:do\s+not|don't|cannot|can't)\s+(?:think|know|confirm)|"
    r"(?:not\s+true|unclear|uncertain)\s+that)\s*$",
    re.IGNORECASE,
)
_CLAUSE_BOUNDARY = re.compile(r"[.!?;\n]")


@dataclass(frozen=True)
class _Relationship:
    person: str
    role: str
    qualifiers: frozenset[str]


def missing_user_relationship(canonical_text: str, speech: str) -> bool:
    """Return whether a detectable positive source relationship is omitted.

    Stored first-person human wording is supported; generated wording must
    address that human as ``you/your``. Only ``fictional`` is omitted from
    descriptive requirements because it annotates the regression memories.
    """

    required = _relationships(_normalize(canonical_text), source=True)
    if not required:
        return False
    stated = _relationships(
        _normalize(speech),
        source=False,
        people=frozenset(item.person for item in required),
    )
    return any(
        not any(
            fact.person == claim.person
            and fact.role == claim.role
            and fact.qualifiers.issubset(claim.qualifiers)
            for claim in stated
        )
        for fact in required
    )


def has_named_user_relationship(canonical_text: str, person: str) -> bool:
    """Return whether source text explicitly binds ``person`` to the user.

    Matching is case-insensitive but otherwise requires the complete parsed
    person name.  Merely mentioning the same token in an unrelated fact, role
    qualifier, or another person's relationship is insufficient.
    """

    normalized_person = " ".join(_normalize(person).casefold().split())
    if not normalized_person:
        return False
    return any(
        relationship.person == normalized_person
        for relationship in _relationships(
            _normalize(canonical_text), source=True
        )
    )


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).replace("\u2019", "'")
    text = re.sub(r"[\u2013\u2014]", ",", text)
    return re.sub(r"(?<=\w)[\-\u2010\u2011](?=\w)", " ", text)


def _relationships(
    text: str, *, source: bool, people: frozenset[str] = frozenset()
) -> frozenset[_Relationship]:
    possessive = _SOURCE_POSSESSIVE if source else r"your"
    human = _SOURCE_HUMAN if source else r"you"
    names = (
        _NAME_PATTERN
        if source
        else re.compile(
            r"(?<![\w'])(?:"
            + "|".join(re.escape(name) for name in sorted(people))
            + r")(?![\w'])",
            re.IGNORECASE,
        )
    )
    direct = re.compile(
        r"[ \t]+(?:is|was|remains)[ \t]+(?:still[ \t]+)?"
        + possessive + r"[ \t]+",
        re.IGNORECASE,
    )
    apposition = re.compile(
        r"[ \t]*(?:[,(:][ \t]*|[ \t]+as[ \t]+)"
        r"(?:(?:(?:who[ \t]+)?(?:is|was|remains)|as)[ \t]+)?"
        + possessive + r"[ \t]+",
        re.IGNORECASE,
    )
    possessives = re.compile(r"\b" + possessive + r"[ \t]+", re.IGNORECASE)
    reversed_link = re.compile(
        r"[ \t]*(?:[,(:][ \t]*)?(?:(?:is|was|named|called)[ \t]+)?",
        re.IGNORECASE,
    )
    coordinated_after = re.compile(
        r"[ \t]+and[ \t]+" + human
        + r"[ \t]+(?:are|were)[ \t]+",
        re.IGNORECASE,
    )
    coordinated_before = re.compile(
        r"\b" + human + r"[ \t]+and[ \t]+$", re.IGNORECASE
    )
    plural_copula = re.compile(r"[ \t]+(?:are|were)[ \t]+", re.IGNORECASE)
    result = set()
    for name in names.finditer(text):
        person = " ".join(name.group().casefold().split())
        if any(word in _NON_NAMES for word in person.split()):
            continue
        for connector in (direct, coordinated_after):
            link = connector.match(text, name.end())
            if link is not None:
                _add_phrase(result, text, person, name.start(), link.end())
        link = apposition.match(text, name.end())
        if link is not None:
            explicit = re.search(r"\b(?:is|was|remains|as)\b", link.group(), re.I)
            _add_phrase(
                result, text, person, name.start(), link.end(),
                require_closing=explicit is None,
            )
        before = text[max(0, name.start() - 200) : name.start()]
        if coordinated_before.search(before):
            link = plural_copula.match(text, name.end())
            if link is not None:
                _add_phrase(result, text, person, name.start(), link.end())
        # Parse only up to this name, so a post-role qualifier cannot swallow
        # another person's name or borrow a role from a later clause.
        for owner in possessives.finditer(
            text, max(0, name.start() - 200), name.start()
        ):
            phrase = _role_phrase(text, owner.end(), limit=name.start())
            if phrase is None:
                continue
            role, qualifiers, end = phrase
            if (
                reversed_link.fullmatch(text[end : name.start()]) is not None
                and _positive_context(text, owner.start(), name.end())
            ):
                result.add(_Relationship(person, role, qualifiers))
    return frozenset(result)


def _add_phrase(
    result: set[_Relationship],
    text: str,
    person: str,
    start: int,
    phrase_start: int,
    *,
    require_closing: bool = False,
) -> None:
    phrase = _role_phrase(text, phrase_start, limit=len(text))
    if phrase is not None:
        role, qualifiers, end = phrase
        remaining = text[end:].lstrip(" \t")
        # Without a closing boundary this may be a vocative: "Theo, your
        # project partner is Alice" assigns the role to Alice, not Theo.
        if require_closing and remaining and remaining[0] not in ",)].!?;\n":
            return
        if _positive_context(text, start, end):
            result.add(_Relationship(person, role, qualifiers))


def _role_phrase(
    text: str, start: int, *, limit: int
) -> tuple[str, frozenset[str], int] | None:
    qualifiers = set()
    cursor = start
    for _ in range(7):
        word = _WORD_PATTERN.match(text, cursor, limit)
        if word is None:
            return None
        token = word.group().casefold()
        role = _IRREGULAR_ROLES.get(token, token.removesuffix("s"))
        if role in _ROLES:
            break
        if token in _STOP_MODIFIERS or "'" in token:
            return None
        if token != "fictional":
            qualifiers.add(token)
        spacing = re.match(r"[ \t]+", text[word.end() : limit])
        if spacing is None:
            return None
        cursor = word.end() + spacing.end()
    else:
        return None
    end = word.end()
    # A nested possessive names somebody else's relationship, not this role.
    if re.match(
        r"[ \t]+[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)?'s\b", text[end:limit]
    ):
        return None
    suffix = re.match(
        r"[ \t]+(?:on|for|in)[ \t]+(?:(?:the|your|our)[ \t]+)?",
        text[end:limit],
        re.IGNORECASE,
    )
    if suffix is not None:
        cursor = end + suffix.end()
        for _ in range(6):
            word = _WORD_PATTERN.match(text, cursor, limit)
            if word is None:
                break
            token = word.group().casefold()
            if token in _STOP_MODIFIERS or "'" in token:
                break
            if token != "fictional":
                qualifiers.add(token)
            end = word.end()
            spacing = re.match(r"[ \t]+", text[end:limit])
            if spacing is None:
                break
            cursor = end + spacing.end()
    return role, frozenset(qualifiers), end


def _positive_context(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 100) : start]
    if _UNCERTAIN_PREFIX.search(before):
        return False
    next_boundary = _CLAUSE_BOUNDARY.search(text, end)
    return next_boundary is None or next_boundary.group() != "?"
