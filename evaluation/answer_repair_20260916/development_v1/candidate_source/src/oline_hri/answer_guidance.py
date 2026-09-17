"""Bounded offline reference notes and task-shaped answer instructions.

These reviewed notes are application knowledge, NOT personal memory. They
ground a few technical concepts without prescribing complete answers or
claiming to verify arbitrary reasoning. No network or extra model call.
Sources and review date travel with the code, not in the speech prompt.
"""

from dataclasses import dataclass
import re

from .task_contract import task_instruction


@dataclass(frozen=True)
class ReferenceNote:
    id: str
    pattern: str
    text: str
    sources: tuple[str, ...]
    reviewed: str = "2026-09-10"


REFERENCE_NOTES = (
    ReferenceNote(
        "cosine_similarity_v1", r"\b(?:cosine similarity|normalized dot product)\b",
        "Cosine similarity divides the dot product by the product of vector lengths: "
        "direction, not magnitude. "
        "For nonzero vectors positive rescaling leaves it unchanged; negative "
        "rescaling reverses its sign. The mathematical formula is undefined "
        "for a zero vector; libraries may choose a convention.",
        ("https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html",),
    ),
    ReferenceNote(
        "sql_transactions_v1", r"\b(?:sqlite|postgresql|postgres)\b",
        "SQLite supports ACID transactions, including commit and rollback. "
        "It is embedded, serverless, and suited to device-local storage; writes "
        "are serialized to one writer per database. PostgreSQL also supports "
        "transactions but runs a database server; consider it for many concurrent "
        "writers or network clients, with extra administration and resources. "
        "Offline alone does not require migration.",
        ("https://www.sqlite.org/transactional.html",
         "https://www.sqlite.org/whentouse.html",
         "https://www.postgresql.org/docs/18/tutorial-transactions.html"),
    ),
    ReferenceNote(
        "rank_fusion_v1", r"\b(?:rrf|reciprocal[ -]rank fusion|raw[ -]score fusion)\b",
        "RRF uses rank positions only: raw score gaps are discarded. It adds "
        "the reciprocal of a constant plus rank across result lists. Raw-score "
        "fusion instead combines numeric scores: it retains score-gap information, "
        "but needs calibration or normalization when scales differ. RRF is a "
        "useful baseline for incompatible score scales, not a guaranteed winner. "
        "Compare on identical judged queries and candidate lists using relevance metrics.",
        ("https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",),
    ),
)
REFERENCE_IDS = frozenset(note.id for note in REFERENCE_NOTES)


def reference_ids_for(request: str) -> tuple[str, ...]:
    """Select at most two reviewed topic notes, never text from a user record."""
    search_feature = re.search(r'\b(?:fts[345]|full[ -]text|virtual tables?)\b', request, re.I)
    transaction_question = re.search(r'\b(?:transactions?|ACID|commit|rollback|writers?|concurrency)\b', request, re.I)
    return tuple(note.id for note in REFERENCE_NOTES
                 if re.search(note.pattern, request, re.I)
                 and not (note.id == 'sql_transactions_v1'
                          and search_feature and not transaction_question))[:2]


def general_response_rule(request: str) -> str:
    rule = (
        "\nRESPONSE_RULE=Complete APPLICATION_REQUEST now; start with the answer. "
        "Use clear English. Preserve requested line breaks, bullets and CSV rows inside the JSON speech string. "
        "Aim for at most 80 speech words, while completing the requested deliverable. Match requested format, counts and constraints. "
        "Use concrete details, not promises to provide details later. "
        "Check that your conclusion follows from your explanation; correct false "
        "premises. State uncertainty when facts are missing. Never invent settings, "
        "resources, guarantees or completed actions. Do not speak JSON field names, "
        "memory selectors or provenance."
    )
    if re.search(r"\b(?:compar\w*|versus|tradeoffs?|trade-offs?)\b", request, re.I):
        rule += (
            " Compare distinct options on the same axes, including each tradeoff. "
            "Justify a recommendation only if requested; avoid arbitrary defaults."
        )
    if re.search(r"\b(?:analy\w*|mitigation\w*|race|racing)\b", request, re.I):
        rule += (
            " Explain the failure mechanism. Pair EACH mitigation with its "
            "remaining limitation; technique names alone do not explain anything."
        )
    planning = bool(
        re.search(r"\b(?:plan|checklist|stages?|steps?|release)\b", request, re.I)
        and (re.search(r"\b(?:create|give|design|build|propose|outline|develop|draft)\b", request, re.I)
             or re.match(r"\s*(?:please\s+)?plan\b", request, re.I))
    )
    technical_plan = planning and bool(re.search(
        r"\b(?:validation|release|deploy\w*|failure|fault|recover\w*|corrupt\w*|restor\w*)\b", request, re.I))
    if technical_plan:
        rule += (
            " PLAN: No introduction. Number the requested stages. "
            "Use this compact form inside EACH stage: action; check observable "
            "result; stop if failure. Give an observable acceptance check, not "
            "'check functionality'. When failure injection is requested, name a "
            "different concrete injected fault in each stage. Include requested "
            "operator records. Use only available local resources."
        )
    if technical_plan and re.search(r"\b(?:recover\w*|corrupt\w*|repair\w*|restor\w*)\b", request, re.I):
        rule += (
            " Recovery: BEGIN by stopping writes/modifications; preserve an untouched copy before repair; "
            "detect or assess damage; restore only from an available verified local "
            "backup; if no usable backup exists, salvage/rebuild a copy locally and "
            "state recovery limits; validate before reuse; prevent recurrence or monitor."
        )
    contract = task_instruction(request)
    if contract:
        rule += " OUTPUT_REQUIREMENTS: " + contract
    ids = reference_ids_for(request)
    if ids:
        rule += " REVIEWED_TECHNICAL_NOTES (not personal memories): " + " ".join(
            note.text for note in REFERENCE_NOTES if note.id in ids
        )
    return rule


def reference_claim_error(speech: str, reference_ids: tuple[str, ...]) -> str | None:
    """Reject two narrow, observed contradictions, not arbitrary false claims.

    A prompt note is not a verifier. These conservative patterns only catch
    direct positive assertions with an unambiguous named subject. Refutations
    and negative assertions do not match; more subtle errors need quality review.
    """
    for clause in re.split(r"[.!?;\n]|\b(?:while|whereas|but)\b", speech, flags=re.I):
        if re.search(r"\b(?:false|incorrect|myth|wrong)\b", clause, re.I):
            continue
        if "sql_transactions_v1" in reference_ids and re.search(
            r"\bSQLite\s+(?:does\s+not|doesn't)\s+support\s+(?:ACID\s+)?transactions?\b",
            clause, re.I,
        ):
            return "answer contradicts the reviewed SQLite transaction note"
        if "rank_fusion_v1" in reference_ids:
            assertion = re.search(
                r"\b(?:RRF|reciprocal[ -]rank fusion)\b(?P<link>.{0,100}?)"
                r"\b(?:preserv\w*|retain\w*)\s+(?:raw\s+)?score[ -]gaps?\b", clause, re.I,
            )
            if assertion and not re.search(
                r"\b(?:not|no|never|neither|doesn't|raw[ -]score fusion)\b",
                assertion.group('link'), re.I,
            ):
                return "answer contradicts the reviewed rank-fusion note"
    return None
