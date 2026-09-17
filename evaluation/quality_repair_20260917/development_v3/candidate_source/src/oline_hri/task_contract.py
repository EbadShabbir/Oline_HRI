"""Bounded request-format checks; these never establish factual correctness.

Only explicit, unambiguous counts are enforced. Checks operate on delivered
text, independently of the model review, and return application-owned feedback.
"""

import csv
from io import StringIO
import re


_NUMBERS = {word: i for i, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
_NUMBER = r"(?:\d{1,3}|" + "|".join(_NUMBERS) + r")"


def _number(value):
    return int(value) if value.isdigit() else _NUMBERS[value.casefold()]


def requested_count(request, unit):
    """Recognize a global exact output count, not source data or an upper bound."""
    pattern = (r"\b(" + _NUMBER + r")[ -]+(?:(?:short|brief|simple|exact|practical|timed|numbered|possible|generic|concrete|pen-and-paper)\s+){0,3}"
               + unit + r"s?\b")
    quotes = list(re.finditer(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', request))
    counts = set()
    for match in re.finditer(pattern, request, re.I):
        if any(quote.start() <= match.start() < quote.end() for quote in quotes):
            continue
        start = max(request.rfind(mark, 0, match.start()) for mark in ".!?;\n") + 1
        prefix = request[start:match.start()]
        suffix = re.split(r"[.!?;\n]", request[match.end():], maxsplit=1)[0]
        if re.search(r"\b(?:do\s+not|don't|never|avoid)\b", prefix, re.I):
            continue
        if re.search(r"\b(?:passage|paragraph|text|source|input|document|file|example)\s+"
                     r"(?:with|of|containing|having|has|uses)\s+$", prefix, re.I):
            continue
        # Ranges, minima, maxima and approximate quantities are not exact counts.
        if re.search(
            r"\b(?:at\s+(?:most|least)|no\s+(?:more|fewer|less)\s+than|up\s+to|"
            r"(?:more|fewer|less)\s+than|min(?:imum)?(?:\s+of)?|max(?:imum)?(?:\s+of)?|"
            r"under|over|about|around|roughly|approximately)\s*$"
            r"|\b(?:between|from)\s+" + _NUMBER + r"\s+(?:and|to)\s*$"
            r"|\b" + _NUMBER + r"\s*(?:[-–—]|to|or|and)\s*$", prefix, re.I,
        ):
            continue
        if re.match(r"\s+(?:at\s+(?:most|least)|minimum|maximum|or\s+(?:fewer|less|more))\b", suffix, re.I):
            continue
        if (re.search(r"\b(?:each|every|per)\b", prefix, re.I)
                or re.match(r"\s*(?:each|apiece|per\b|for\s+(?:each|every)\b)", suffix, re.I)):
            continue
        if re.search(r"\b(?:limit|keep)\b", prefix, re.I) and not re.search(r"\bexactly\s*$", prefix, re.I):
            continue
        if re.match(r"\s+(?:can|could|may|might|is|are|was|were)\b", suffix, re.I):
            continue
        qualifier = (r"(?:(?:exactly|only|just)\s+)?(?:(?:a|an)\s+)?"
                     r"(?:(?:friendly|polite|formal|informal|brief|short|simple|concise)\s+)?")
        direct = re.search(
            r"\b(?:write|give|provide|return|use|include|produce|compose|draft|output|suggest|choose|pick)"
            r"\s+(?:(?:me|us)\s+)?" + qualifier + r"$", prefix, re.I)
        formatted = (re.search(r"\b(?:in|using|with|as|to)\s+" + qualifier + r"$", prefix, re.I)
                     and re.search(r"\b(?:write|give|provide|return|respond|answer|reply|use|"
                                   r"explain|describe|summarize|rewrite|shorten|condense|format|"
                                   r"compose|draft|produce|render|output|keep|limit)\b", prefix, re.I))
        prescribed = re.search(
            r"\b(?:answer|reply|response|output)\s+(?:must|should)\s+"
            r"(?:have|contain|use|include|be|consist\s+of)\s+" + qualifier + r"$", prefix, re.I)
        conjoined = (re.search(r"\band\s+" + qualifier + r"$", prefix, re.I)
                     and re.search(r"\b(?:(?:write|give|provide|return|use|include|compose|draft|output)\s+"
                                   r"|(?:answer|respond|reply|explain|describe|summarize)\s+(?:in|with|using)\s+)"
                                   + qualifier + _NUMBER + r"\b", prefix, re.I))
        standalone = (re.fullmatch(r"\s*(?:exactly|only)\s+", prefix, re.I)
                      or not prefix.strip() and re.match(r"\s+only\b", suffix, re.I))
        if direct or formatted or prescribed or conjoined or standalone:
            counts.add(_number(match.group(1)))
    return counts.pop() if len(counts) == 1 else None


def csv_output_requested(request):
    """Require an output/conversion directive; a discussion of CSV is ordinary prose."""
    unquoted = re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', " ", request)
    for sentence in re.split(r"[.!?\n]", unquoted):
        # Retain the complete conversion directive when semicolons separate
        # supplied data, and also recognize an explicit later output directive.
        for clause in (sentence, *sentence.split(";")[1:]):
            clause = re.sub(r"^\s*(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?",
                            "", clause, flags=re.I).strip()
            if re.search(r"\b(?:do\s+not|don't|never|avoid)\b", clause, re.I):
                continue
            if re.fullmatch(r"(?:only\s+CSV|CSV\s+only)[;,\s]*", clause, re.I):
                return True
            if re.match(r"(?:return|output|emit|produce|provide|give|use)\s+"
                        r"(?:(?:only|plain|valid|raw)\s+)*CSV\b", clause, re.I):
                return True
            if re.match(r"(?:convert|format|render|rewrite|return|output|respond|reply|give|provide)\b"
                        r".*?\b(?:to|into|as|in)\s+(?:(?:plain|valid|raw)\s+)*CSV\b", clause, re.I):
                return True
    return False


def requested_csv_header(request):
    if not csv_output_requested(request):
        return None
    pattern = r"\bheader\s+(?:(?:must\s+be|should\s+be|is)\s+)?[\"'`]?([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)+)"
    for match in _positive_directives(pattern, request):
        return ",".join(cell.strip() for cell in match.group(1).split(","))
    return None


def _unquoted(request):
    return re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', " ", request)


def _negated_directive(request, start):
    boundary = max(request.rfind(mark, 0, start) for mark in ".!?;\n") + 1
    return bool(re.search(r"\b(?:do\s+not|don't|never|avoid)\b", request[boundary:start], re.I))


def _positive_directives(pattern, request):
    quotes = tuple(re.finditer(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', request))
    return (match for match in re.finditer(pattern, request, re.I)
            if not _negated_directive(request, match.start())
            and not any(quote.start() <= match.start() < quote.end() for quote in quotes))


def scalar_output_requested(request):
    """A direct request for only one integer; mentioning an integer is insufficient."""
    text = _unquoted(request)
    match = re.search(r"\b(?:return|output|give|answer\s+with)\s+(?:only|just)\s+"
                      r"(?:the\s+|a\s+)?(?:whole\s+number|integer)\b", text, re.I)
    return bool(match and not _negated_directive(text, match.start()))


def numbered_output_requested(request):
    text = _unquoted(request)
    return any(requested_count(text, unit) is not None and re.search(
        r"\b" + _NUMBER + r"[ -]+(?:(?:short|brief|simple|exact|practical|timed)\s+){0,2}"
        r"numbered\s+" + unit + r"s?\b", text, re.I)
        for unit in ("step", "line", "item"))


def requested_line_prefixes(request, count):
    """Copy labels only from an explicit prefix directive, never from task data."""
    if not count:
        return ()
    directive = next(_positive_directives(r"\b(?:prefixes|labels|(?:start|begin)\s+(?:(?:the|their)\s+)?(?:lines?|text)\s+with)\s*:?\s*([^.!?\n]+)", request), None)
    if not directive:
        return ()
    labels = re.findall(r"\b([A-Za-z][A-Za-z -]{0,24}):", directive.group(1))
    labels = [re.sub(r"^(?:and\s+)", "", label).strip() + ":" for label in labels]
    return tuple(labels) if len(labels) == count else ()


def allocation_budget(request):
    """An explicit sum requirement, rather than every mentioned duration."""
    matches = list(re.finditer(
        r"\b(?:total(?:ing|ling|s|\s+of)?|sum(?:ming)?\s+to)\s+(" + _NUMBER + r")\s+minutes?\b",
        request, re.I))
    values = {_number(m.group(1)) for m in matches}
    return values.pop() if len(values) == 1 else None


def _sentences(text):
    def protect(match):
        abbreviation = match.group().replace(".", "·")
        if (re.fullmatch(r"[ap]\.m\.", match.group(), re.I)
                and re.match(r"\s+[A-Z]", text[match.end():])):
            abbreviation = abbreviation[:-1] + "."
        return abbreviation
    protected = re.sub(r"\b(?:[ap]\.m\.|e\.g\.|i\.e\.|Mr\.|Mrs\.|Ms\.|Dr\.)",
                       protect, text, flags=re.I)
    # A bare arithmetic expression is not a prose sentence. Decimal points
    # and clock notation are not sentence boundaries.
    parts = re.split(r"(?<!\d)[.!?]+(?:[\"'’”])?(?:\s+|$)|(?<=\d)[.!?]+(?:\s+|$)", protected)
    return [part for part in parts if re.search(r"[A-Za-z]", part)]


def word_occurrences(request):
    """Only explicit positive requests for one quoted word and an exact count."""
    result = []
    for match in re.finditer(
            r"\b(?:include|use)\s+the\s+word\s+['\"]([A-Za-z]{1,32})['\"]\s+"
            r"exactly\s+(once|twice|" + _NUMBER + r"\s+times)\b", request, re.I):
        prefix = request[max(0, match.start()-15):match.start()]
        if re.search(r"\b(?:not|never|don't)\s*$", prefix, re.I):
            continue
        quantity = match.group(2).lower()
        count = {"once": 1, "twice": 2}.get(quantity)
        result.append((match.group(1), count if count is not None else _number(quantity.split()[0])))
    return tuple(result)


def task_contract_issues(request, answer):
    issues = []
    for word, count in word_occurrences(request):
        if len(re.findall(r"\b" + re.escape(word) + r"\b", answer, re.I)) != count:
            issues.append("requested_word_count")
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    if scalar_output_requested(request) and not re.fullmatch(r"[+-]?\d+", answer.strip()):
        issues.append("requested_scalar")
    if numbered_output_requested(request):
        count = requested_count(request, "step") or requested_count(request, "line") or requested_count(request, "item")
        if count and (len(lines) != count or any(
                not re.match(r"^" + str(index) + r"[.)]\s+\S", line)
                for index, line in enumerate(lines, 1))):
            issues.append("requested_numbering")
    bullets = requested_count(request, r"bullet(?:\s+point)?")
    if bullets is not None and (len(lines) != bullets or any(
            not re.match(r"^(?:[-*•]|\d+[.)])\s+\S", line) for line in lines)):
        issues.append("requested_bullet_count")
    count = requested_count(request, "line")
    if count is not None and len(lines) != count:
        issues.append("requested_line_count")
    count = requested_count(request, "sentence")
    if count is not None and len(_sentences(answer)) != count:
        issues.append("requested_sentence_count")
    count = requested_count(request, "equation")
    if count is not None and answer.count("=") != count:
        issues.append("requested_equation_count")
    if csv_output_requested(request):
        try:
            rows = list(csv.reader(StringIO(answer), strict=True))
        except csv.Error:
            rows = []
        header = requested_csv_header(request)
        if (len(rows) < 2 or len(rows[0]) < 2
                or any(len(row) != len(rows[0]) or not all(cell.strip() for cell in row) for row in rows)
                or (header and rows[0] != header.split(","))
                or "```" in answer):
            issues.append("requested_csv")
    minutes = allocation_budget(request)
    if minutes is not None:
        # Sum step durations, excluding an explicitly labelled overall total.
        durations = []
        for match in re.finditer(r"\b(\d{1,3})\s*(?:minutes?|mins?)\b", answer, re.I):
            if re.search(r"\btotal\s*[:=]?\s*$", answer[max(0, match.start()-15):match.start()], re.I):
                continue
            durations.append(int(match.group(1)))
        if len(durations) < 2 or any(value < 1 for value in durations) or sum(durations) != minutes:
            issues.append("requested_time_allocations")
    return tuple(issues)


TASK_FEEDBACK = {
    "requested_scalar": "Return only the computed integer, without an equation, units or explanatory words.",
    "requested_numbering": "Use the requested consecutive numbered lines starting with 1., with no extra introduction or final line.",
    "requested_word_count": "Use each explicitly counted word exactly the requested number of times across the whole answer.",
    "requested_bullet_count": "Use exactly the requested number of bullet points, each on its own line, with no introduction.",
    "requested_line_count": "Use exactly the requested number of nonempty lines; put a JSON-escaped newline between them.",
    "requested_sentence_count": "Use exactly the requested number of complete sentences and no extra introductory sentence.",
    "requested_equation_count": "Include exactly the requested number of equations, each with one equals sign.",
    "requested_csv": "Return only valid CSV, with the requested header followed by every supplied row in order; use JSON-escaped newlines.",
    "requested_time_allocations": "Give a duration in digits and minutes for each step; their sum must equal the requested total. Include every requested deliverable.",
}


def task_instruction(request):
    rules = []
    if scalar_output_requested(request):
        rules.append(TASK_FEEDBACK["requested_scalar"])
    if numbered_output_requested(request):
        rules.append(TASK_FEEDBACK["requested_numbering"])
    if requested_count(request, "activity") == 1:
        rules.append("Choose one specific activity, not a list of alternatives. Explain its first concrete action using the available supplies.")
    for word, count in word_occurrences(request):
        rules.append(f"Use the word '{word}' exactly {count} times across the whole answer.")
    for unit, label in ((r"bullet(?:\s+point)?", "bullet points on separate lines"),
                        ("line", "nonempty lines"), ("sentence", "sentences"),
                        ("equation", "equations"), ("item", "actual list items"),
                        ("phase", "phases"), ("step", "steps")):
        count = requested_count(request, unit)
        if count is not None:
            rules.append(f"Exactly {count} {label}.")
    minutes = allocation_budget(request)
    if minutes is not None:
        rules.append(f"Assign a positive integer duration to each step, written as 'N minutes'; all step durations must sum to {minutes}. Do not substitute an overall timer for step allocations.")
    if csv_output_requested(request):
        rules.append("Speech contains only CSV: requested header, then each data row on its own line; no explanation or code fence.")
    return " ".join(rules)


def clarification_question(request):
    """Ask for the unresolved task/referent, without guessing a missing value."""
    text = request.casefold()
    if re.search(r"\b(?:convert|conversion)\b", text):
        return "What unit is the value in, and which unit should I convert it to?"
    if re.search(r"\b(?:replace|pronoun|refer)\b", text) and re.search(r"\b(?:they|he|she|them|him|her)\b", text):
        return "Who does the pronoun refer to? Please name the intended person."
    if re.search(r"\blabels?\b", text):
        return "Which label would you like me to change, or should I change both?"
    if re.search(r"\b(?:numbers?|calculate|calculation|work\s+it\s+out)\b", text):
        return "What calculation would you like me to do with those numbers?"
    if re.search(r"\benough\b", text):
        return "Enough of what, and for what purpose?"
    if re.search(r"\b(?:fix|repair)\s+(?:it|that|this)\b", text):
        return "What would you like me to fix, and what is going wrong?"
    if re.search(r"\b(?:reply|respond)\s+to\b", text):
        return "Who should the reply be addressed to? Please give their full name."
    if re.search(r"\b(?:messages?|notes?|drafts?)\b", text):
        return "Which message or draft would you like me to change?"
    if re.search(r"\b(?:other\s+one|options?|titles?|choices?|versions?)\b", text):
        return "Which option do you mean? Please name the one you want."
    return "What would you like help with, and what result do you want?"


def missing_detail_reply(request, missing_fact="stored personal fact"):
    """Name the missing subject using only words in the user's recall question.

    This extracts no purported answer and does not interpret quoted assistant
    guesses as facts. If the grammar is unclear it falls back to a fact category.
    """
    questions = list(re.finditer(r"\b(?:what|which|who|where|when|on\s+what)\b[^?]*\?", request, re.I))
    question = questions[-1].group() if questions else request
    focus = re.search(r"\b(?:what|which)\s+(.+?)\s+(?:did\s+I|have\s+I|do\s+I)\b", question, re.I)
    if focus:
        subject = focus.group(1).strip()
        subject = re.sub(r"\bmy\b", "your", subject, flags=re.I)
        question_text = f"Could you remind me of the {subject}?"
    else:
        focus = re.search(r"\bwhat\s+is\s+(?:the\s+)?(.+?)\s+I\s+(?:told|said|mentioned)\b", question, re.I)
        if focus:
            question_text = f"Could you remind me of the {focus.group(1).strip()}?"
        elif re.search(r"\b(?:what|which)\b.+?\b(?:is|are)\b", question, re.I):
            direct = re.split(r",?\s+according\s+to\b", question, maxsplit=1, flags=re.I)[0].rstrip(" ?.")
            direct = re.sub(r"\bmy\b", "your", direct, flags=re.I)
            direct = re.sub(r"\bour\b", "your", direct, flags=re.I)
            question_text = direct + "?"
        elif re.search(r"\bwhere\b", question, re.I):
            question_text = "Could you remind me of the place you mean?"
        elif re.search(r"\bwho\b", question, re.I):
            named_relation = re.search(
                r"\bwho\s+is\s+([^?.!\n]+?)\s+(?:in\s+relation\s+to|to)\s+me\b",
                question, re.I)
            if named_relation:
                question_text = f"Could you remind me how {named_relation.group(1).strip()} is related to you?"
            else:
                question_text = "Could you remind me of the person's name?"
        else:
            label = {"personal preference": "preference", "personal schedule": "time or date",
                     "personal relationship": "person or relationship", "personal constraint": "requirement",
                     "past event": "event", "personal context": "context"}.get(missing_fact, "detail")
            question_text = f"Could you remind me of the {label}?"
    explanation = "I don't have that earlier information available. "
    if (re.search(r"\bassistant\b", request, re.I)
            and re.search(r"\b(?:guess\w*|hunch|unsupported)\b", request, re.I)):
        explanation += "An assistant's guess does not establish what you told me. "
    return explanation + question_text
