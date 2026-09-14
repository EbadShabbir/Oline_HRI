"""Small application-authored software runbooks, not general model reasoning.

Only recognized offline software requests without extra constraints are eligible.
Never execute a step, promise recovery, or infer hardware/operator state.
"""

import re

from .grounded_composition import ComposedAnswer


OPERATIONAL_CONSTRAINTS = frozenset({
    'bounded_software_validation', 'bounded_software_release',
    'bounded_database_recovery',
})


def compose_operational_plan(request: str) -> ComposedAnswer | None:
    if not re.search(r'\b(?:offline|local|disconnected)\b', request, re.I):
        return None
    if not re.search(r'\b(?:software|python|service|kiosk|application|database|assistant|conversational robot)\b', request, re.I):
        return None
    if not re.search(r'\b(?:plan|checklist)\b', request, re.I):
        return None
    if re.search(r'\b(?:cost|budget|estimate|risk|translate|poem|rhyme|json|table|verbatim|only|omit|exclude|except|avoid|never|read-only|read only|minutes?|hours?|days?|weeks?|windows|docker|kubernetes|medical|financial|Spanish|French|Arabic|Hindi|Russian|Chinese|German|Japanese)\b', request, re.I):
        return None
    if not request.isascii() or re.search(
        r'\bwithout\b(?!\s+(?:assuming\s+)?(?:network|internet)\s+access\b|\s+(?:usable\s+|verified\s+)?backups?\b)',
        request, re.I,
    ):
        return None
    if re.search(r"\b(?:do not|don't|must not)\b", request, re.I):
        return None
    numbers = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
               'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
    counts = re.findall(r'\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)[ -]+(?:stages?|steps?)\b', request, re.I)
    counts = {numbers[c.lower()] if c.lower() in numbers else int(c) for c in counts}
    if len(counts) > 1:
        return None
    count = next(iter(counts), None)
    result = None
    if re.search(r'\b(?:validation|test|testing)\b', request, re.I) and not re.search(r'\brelease\b', request, re.I):
        if count not in (3, 5):
            return None
        faults = [
            'Break config; expect refusal; stop on acceptance.',
            'Remove model; expect error; stop on silence.',
            'Inject timeout; expect bounded error; stop on hangs.',
            'Corrupt storage; expect rejection; stop on overwrite.',
            'Interrupt writes; restart; verify recovery; stop on mismatch.',
        ]
        if count == 3:
            faults = [faults[0], faults[2], faults[3]]
        speech = 'Use isolated copies. ' + ' '.join(f'{n}. {text}' for n, text in enumerate(faults, 1))
        speech += ' Log results; roll back failed builds.'
        result = ComposedAnswer(speech, 'bounded_software_validation')
    elif re.search(r'\brelease\b', request, re.I):
        if count not in (None, 3) or re.search(r'\b(?:no|without)\s+(?:usable\s+|verified\s+)?backups?\b', request, re.I):
            return None
        result = ComposedAnswer(
            '1. Prepare a versioned local package and rollback copy; verify dependencies and backup readability; stop if missing. '
            '2. Install on a test copy; run startup, smoke and restart tests; reject failures. '
            '3. Release to one instance; compare errors and latency with baseline; restore the prior version on regression. '
            'Record version, checks, errors and rollback steps for the operator.',
            'bounded_software_release',
        )
    elif re.search(r'\b(?:recover\w*|contingency)\b', request, re.I) and re.search(r'\bcorrupt\w*\b', request, re.I):
        if count is not None:
            return None
        no_backup = re.search(r'\b(?:no|without)\s+(?:usable\s+|verified\s+)?backups?\b', request, re.I)
        restore = '' if no_backup else 'Restore a verified local backup if available; otherwise '
        salvage = 'salvage' if restore else 'Salvage'
        result = ComposedAnswer(
            'Stop writes; preserve the original and work on a copy. Assess corruption. '
            + restore + salvage + ' recoverable rows into a new local database or rebuild from available records. '
            'Verify row counts, constraints and application smoke tests before switching; quarantine failed output. '
            'Complete recovery cannot be guaranteed. Record losses and test future backups.',
            'bounded_database_recovery',
        )
    if result and (len(result.speech.split()) > 80 or len(result.speech) > 850):
        return None
    return result
