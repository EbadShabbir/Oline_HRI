# Proposed second repair: current relationship requests

Status: **design only; not applied, not live-tested**. Prepared by the validation
assistant on 14 September 2026 while the first repair collection remained
frozen. This file does not revise any answer, judgment, source snapshot or
checkpoint from that collection. Human validation remains pending.

## Diagnosed failure

The independent [withheld-answer diagnostic](withheld_diagnostics_v1.json)
identifies two withheld cm04 correction restart answers. The authorized record
is `Your walking partner is Niko Fern.` and the question is:

> Returning to my earlier walking partner information, who is my current walking partner?

`conversation._collaborator_request_link` compares every query qualifier's topic
term with all canonical-text topic terms. It therefore requires the literal
`current` token in this record, even though the present-tense relationship and
the real lifecycle checks establish the current authorized replacement.

The first repair changed answer-to-source relationship coverage. This is a
different gate: query-to-source relationship linking. Keeping those mechanisms
distinct explains why the first repair did not eliminate these two withholds.

Inspected production hashes, unchanged while preparing this proposal:

| File | SHA-256 |
| --- | --- |
| `src/oline_hri/conversation.py` | `0717344dbf1ae1f8cfa33914a1c2e471513bc71cdf6308fa0aebd9f3c18dabe6` |
| `src/oline_hri/relationships.py` | `759d2a6c671581ffd5db2b07e14a89b81d90fc58ed5fd3625bcf6ec9860b80f6` |
| `src/oline_hri/memory_evidence.py` | `c0b1b0744f022fd593501e7a7310040309b4d198ba56435643ba14f2645d22e7` |
| `tests/test_memory_lifecycle_validation.py` | `d22b48a23278bf4500588d7f96dc1b02363114815e96fd16898539428e11912f` |

## Bounded implementation design

Apply only after `run_v1` is sealed and its complete integrity audit passes.
Change `relationships.py`, `conversation.py` and focused offline tests. Preserve
the first repair and label the next source freeze and cm04 live collection as a
second repair, with separate results.

Extend the existing parsed relationship lookup with optional filters, keeping
all defaults compatible with existing callers. A concrete candidate signature
is:

```python
def has_named_user_relationship(
    text: str,
    person: str,
    *,
    current_only: bool = False,
    role: str | None = None,
    qualifiers: frozenset[str] = frozenset(),
    addressed_to_user: bool = False,
) -> bool:
    ...
```

The filtered lookup must find **one parsed relationship witness** with the same
complete normalized person name, the requested role and every requested domain
qualifier. Test qualifiers against that witness, not all words in the record.
Reuse the existing `_Relationship.past_tense` and parsed qualifiers. For
`current_only=True`, reject a past-tense witness or one qualified as `former`,
`previous`, `past` or `old`; retain existing rejection of negative, uncertain and
third-party statements. A literal `current` in the source is optional. A
statement such as `Niko Fern was your current walking partner` remains past
tense and must fail. Do not infer recency from a name or from unrelated words.

For generated speech, `addressed_to_user=True` must use the existing response
parser (`source=False`, constrained to the supplied person's name). This
prevents `my partner` or a third person's partner from satisfying `your partner`.
Preserve first-person stored memories when this option is false.

In `_collaborator_request_link`, capture the requested role explicitly. Preserve
the existing behavior for requests without `current`. For an explicit current
request, remove only that temporal marker from its qualifier set, then use the
filtered lookup with `current_only=True`, the requested role and every remaining
domain qualifier. The cm04 query therefore requests a current **walking
partner**, with all three properties bound to the same person. It does not
become an unqualified request for any relationship.

Do not let `_OWNER_NAMED_COLLABORATOR_PATTERNS` return true before this current
check. A named owner's relationship alone does not establish that owner's
identity as the current user. The narrow new branch may fail closed on those
forms; preserve their existing behavior for non-current queries. Similarly, do
not make `collaborator` an alias for every relationship role. If retaining the
existing explicit partner/collaborator synonym, normalize only those two role
tokens symmetrically and still require the parsed person and domain qualifiers.
Unsupported source grammar should remain unsupported.

The delivery validator needs the same current-only witness condition. For an
explicit current-partner question, derive eligible people from cited authorized
source witnesses, and require the delivered speech to state a matching current
relationship to at least one of those people. If there are multiple required
people, retain the existing citation and relationship coverage requirements for
each; this change must not reduce them. Reject an answer supported only by a
past/former or differently qualified speech witness.

This delivery check matters because `_cited_named_collaborator_names` presently
collects names only from named-owner forms; ordinary `Your walking partner is
Niko Fern` produces no names there. Also, `missing_user_relationship` enforces
current status only when the canonical text itself says `current`. Fixing only
source linking would leave `Niko Fern was your walking partner` able to cover a
present-tense canonical fact for a current question.

Do not synthesize a replacement answer or bypass a citation, freshness check,
storage permission, deletion or expiry boundary. The real model must still
produce the response and all unchanged validation checks must run.

## Offline regression plan, frozen before inference

Tests must exercise the shared parser, `_collaborator_request_link` and a real
`Conversation.send` path using fake transport only. Label these observations as
offline tests, never live answers.

| Case | Expected result |
| --- | --- |
| Current walking-partner question; `Your walking partner is Niko Fern.` | Link succeeds; present-tense supported answer delivers. |
| Same question with the exact retained-memory restart preamble | Same outcome; no requirement to repeat `current`. |
| Equivalent source `Niko Fern is your walking partner.` | Same outcome. |
| Source explicitly says `current walking partner` | Same outcome. |
| Query and source use a different fictional person's full name and a garden-project role | Generalized positive control; no fixture-specific matching. |
| `Niko Fern was your walking partner.` | Current-only source lookup fails. |
| `Your walking partner was Niko Fern.` or `You and Niko Fern were walking partners.` | Current-only source lookup fails. |
| `Niko Fern was your current walking partner.` | Fails despite literal current marker. |
| Former/previous/past/old walking partner source | Fails; temporal qualifier is not dropped. |
| Negative or uncertain source; another person's walking partner | Fails. |
| Niko is a friend; walking partner is mentioned elsewhere | Fails; domain and role cannot be borrowed across relationships. |
| `Niko Fern is your chess partner`; unrelated walking discussion elsewhere | Fails; domain cannot be borrowed from whole-record topic terms. |
| Niko is your partner, without walking qualifier | Fails; missing requested domain is not inferred. |
| Current walking-partner source; answer names Elora Vale | Existing person/citation coverage rejects it. |
| Current source; answer calls Niko a former partner, says `was`, or drops `walking` | Delivery check rejects it. |
| Current source; answer gives another person's walking partner | Delivery check rejects it. |
| A legitimate non-current/historical relationship request | Existing behavior remains unchanged. |
| Record deleted, expired, superseded, or snapshot invalidated | Existing lifecycle exclusion and uncertainty behavior remain unchanged. |

Run the focused relationship, lifecycle-validation, conversation-routed,
grounding-review, memory-evidence and memory-reliability suites. Include the
current first-repair integration regressions and report any changed assumptions.
Review the diff independently before creating the second source freeze.

## Separate live follow-up

After the complete first repair is sealed and reviewed, freeze the second
runtime configuration and execute the authored **full cm04 lifecycle: three
independent branches and 24 scored checkpoints**, including correction,
deletion, controlled expiry, retained/fresh history and real process restarts.
Keep the original schedule, independent expected ledger and rubric unchanged.
Use fresh isolated persistent databases and serialized installed-model
inference under the existing resource guards. Preserve every attempted
checkpoint and failure.

Use new blinded assistant judgments and audit all actual storage, retrieval,
model input, generation, validation and restart evidence. Report first-repair
and second-repair observations separately, including both original withheld
answers. A successful second run cannot replace those original outcomes, and
it does not establish performance across untested scenarios or spoken/power-loss
conditions. No live follow-up has been executed as part of this proposal.
