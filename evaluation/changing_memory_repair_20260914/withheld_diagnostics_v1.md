# Two withheld walking-partner answers: unblinded diagnosis

Both repaired-system responses were withheld unnecessarily by a remaining collaborator request-link check. Storage and retrieval supplied the current replacement, and generation produced a useful, supported answer. **Neither answer was delivered, so both remain unsuccessful recall.** This is an unblinded assistant diagnostic assessment, not a revision of the original blinded judgments; human validation remains pending.

The two checkpoints are `cm04_correction_restart_retained` and `cm04_correction_restart_fresh`. Both ask:

> Returning to my earlier walking partner information, who is my current walking partner?

The frozen ledger requires **Niko Fern** and forbids Elora Vale and the unrelated historical-control venue, Birch Lodge. Both raw model responses say:

> Your current walking partner is Niko Fern.

The raw speech gives exactly the requested current person and role, with no unrelated detail or forbidden value. “Current” answers the question and is consistent with the freshly validated active replacement; it does not invent an additional relationship. This raw-answer usefulness assessment is diagnostic and unblinded. It is separate from the immutable delivered no-answer scores.

## Evidence and failure stage

| Checkpoint | Trace source | Actual generator | Delivered answer | Failure |
|---|---|---|---|---|
| `cm04_correction_restart_retained` | `run_v1/cm04_correction/restart/answers.jsonl`, line 1 | `qwen3:0.6b` | null | `robot response lacks evidence for the requested collaborator` |
| `cm04_correction_restart_fresh` | Same file, line 2 | `qwen3:0.6b` | null | Same |

Both actual generation requests contain the structured record `mem_2b1f3f05adc94e1cb7c89aaa6ab6b616`, whose canonical text is “Your walking partner is Niko Fern.” The real retrieval output contains that active confirmed replacement, with `supersedes_id` pointing to the original record. Its validity begins at logical `2026-10-01T12:01:00Z` and its retention deadline is `2026-10-08T12:00:00Z`.

Each checkpoint has two successful actual freshness checks at its frozen logical time, `2026-10-01T12:02:01+00:00`, one before and one after generation. Each generator receives only the system message and the current request/evidence message; prior conversation is not forwarded. Thus the retained/fresh pair reaches the same relevant evidence and produces the same answer. This is not a storage, retrieval, snapshot, or retained-history disclosure failure.

The generation schema has no speech `enum` constraint, so this is not failure of the new location-extraction composition path. The error is explicitly recorded in the `validation` span after generation. The frozen collector's convenience field `supplied_evidence_envelopes` is empty on these rejected rows, but the actual generation messages preserve the envelope. The separately approved analysis parser recovers it; the full request is included in the diagnostic JSON.

## Remaining validator defect

The frozen implementation calls `_require_requested_named_collaborator` at [conversation.py:2142](frozen_v2/source/src/oline_hri/conversation.py). It asks `_collaborator_request_link` at [conversation.py:2271](frozen_v2/source/src/oline_hri/conversation.py) to verify the cited record against the question.

That request-link function extracts the question's qualifiers, `current walking`, and requires all their topic terms to occur literally in the canonical record. The relevant sets are:

- Query qualifier terms: `current`, `walk`.
- Canonical record terms: `fern`, `niko`, `partner`, `walk`.

`current` is absent from the stored wording, so the request-link returns false and validation reports missing collaborator evidence. The supplied present-tense relationship is nevertheless the current authorized replacement. The check conflates a requested lifecycle state with an extra lexical relationship qualifier.

A pure function probe imported the exact frozen source and reproduced the recorded rejection using the actual question, canonical record, and raw speech. Removing only `current` from the probe question made this specific function accept the same evidence and speech. This was a diagnostic function call, not model inference, a changed experimental question, or a rerun.

The repaired `relationships.missing_user_relationship` returns false for this canonical/raw pair, correctly recognizing that the named relationship is covered. That repair does not affect the separate failing request-link function. AST comparison confirms both `_require_requested_named_collaborator` and `_collaborator_request_link` are unchanged from the original baseline. The remaining defect is therefore localized to that preexisting validator gate.

## Frozen judgments and reproducibility

The independently frozen [batch receipt](review_receipts/batch_01.json) binds both reviewer files and confirms no semantic disagreements before diagnostic access. Both checkpoints map to the same exact blind packet, `b_f9b04f8476266e9830592907`. Each original reviewer assigned `no_delivered_answer`, `useful_correct=false`, and `forbidden_disclosure=false`. Those judgments remain unchanged. The absence of disclosure is safe withholding, but withholding these useful supported raw answers is an unnecessary rejection.

[withheld_diagnostics_v1.json](withheld_diagnostics_v1.json) contains the exact two raw generation calls, recovered supplied records, retrieval results, freshness checks, failed validation spans, expected ledger entries, frozen original judgments, and input paths/hashes. Its SHA-256 is `e200223184007f07ce97b8ea5ff8d0bf24f5abc264c0e6ea6b8bbbed4a8b0e91`.

The reproducible command is `.venv/bin/python evaluation/changing_memory_repair_20260914/withheld_diagnostics_v1.py`. The read-only source, log, and command/hash receipt are adjacent. The source verifies the freeze, completed branch, process fragment, review-packet seals, and reviewer receipt hashes before diagnosis. No runtime change, model call, rescoring, or batch02 inspection occurred, and no diagnostic information was sent to either blinded reviewer.
