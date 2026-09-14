# Memory routing reliability: diagnosis and repair design

Status: implementation complete, candidate validation in progress. The
[implementation and validation record](routing_reliability_20260914/README.md)
tracks the four-mode runtime, independent evidence boundary, reply checks,
and measured promotion decision. This document preserves the original
diagnosis and acceptance criteria. The earlier general-advice patch alone
does not establish general routing reliability.

## What failed

The production Boolean `memory_required` currently decides both whether to
retrieve personal records and whether missing evidence must replace the whole
answer with an abstention. A false positive therefore blocks ordinary help.
The broad first-person/question rule and the probabilistic classifier can each
cause the error. Adding more accepted advice phrases does not repair that
coupling.

An independently authored, frozen 24-case diagnostic set was replayed once
against the current local router on 2026-09-14. Its author did not inspect
production routing before writing the cases. Twenty cases had binary labels;
four ambiguous or mixed cases were deliberately excluded from binary scoring.

| Group | Cases | Raw classifier errors | Final routing errors |
| --- | ---: | ---: | ---: |
| General/current-input questions | 12 | 6 | 5 |
| Required personal recall/planning | 8 | 3 | 1 |
| Ambiguous/mixed, unscored | 4 | — | — |

The rules corrected some classifier mistakes, so simply removing every rule
would also regress this diagnostic. This small, single-pass development set is
not a benchmark accuracy estimate or a speech-recognition evaluation. After
inspection, it becomes development/regression data, not a future holdout.

Reproduction and raw evidence are under
[`tmp/routing_robustness_20260914`](../tmp/routing_robustness_20260914/), including
the cases, runner, raw classifier results, source/configuration hashes and
summary. The runner used local Qwen and did not access personal records or
generate answers. The earlier 212 passing unit tests checked defined code
behavior; they did not establish model generalization.

## Request contract from the repair design

Replace the retrieval Boolean as the primary semantic contract with a strictly
validated mode. Preserve grammatical form, since disclosure handling uses it.
Keep model-size selection independent, and preserve the raw classifier outputs
for audit. Avoid redundant model-written Boolean and mode fields that can
contradict one another.

| Mode | Meaning | Response when personal evidence is absent |
| --- | --- | --- |
| `none` | Current supplied inputs and general knowledge suffice | Answer the current question |
| `optional` | Personalization could improve an otherwise answerable question | Give a general answer using current inputs |
| `required` | The requested answer depends on an unstated personal fact | Explain the missing fact and ask for it; do not invent it |
| `clarify` | The intended task or necessary referent is unresolved | Ask one short clarification question |

Examples of the distinction: advice for a currently supplied problem normally
does not require recall; asking what helped that person previously does.
All constraints supplied in the current message do not become a memory
dependency merely because they are personal. A mixed request should preserve
its answerable general part while identifying its missing personal part.

The deployed candidate predicts dependency with a local supervised classifier
over the existing BGE embeddings and learned word/character features. It uses
empirically fitted score-margin rejection thresholds. The first frozen
candidate clarified on uncertainty and failed release validation because it
withheld too many ordinary answers. The revised candidate adds one bounded
larger review, with clarification when that review is unresolved or invalid.
Missing-fact labels are generic application labels, not model
explanations. Grammatical form is only a punctuation hint in this adapter.
Neither a class label nor a margin authorizes a personal fact. The separate
Qwen semantic-router experiments remain reproducible; their development
failures are not treated as successful validation.

## Response and authorization boundaries

1. Retrieval benefit and answerability are separate decisions. Empty or
   irrelevant optional retrieval cannot trigger a whole-answer refusal.
2. Every used personal record still passes profile, consent, relevance,
   correction, deletion, expiry and current-snapshot checks. A classifier or a
   larger model cannot authorize a personal fact.
3. Personal dialogue history needs a route-independent provenance boundary.
   Currently `omit_generation_history = memory_requested` protects history
   only when the route is correct. With a false-negative route, old disclosures
   can reach a general generator. Keep reference/task context separately from
   personal factual evidence; withhold or freshly authorize personal values.
   A prompt telling the model not to use old facts is not an equivalent check.
4. Uncertain or inconsistent decisions can receive one bounded review by the
   existing larger model, followed by clarification if unresolved. Do not
   equate a model's self-reported confidence with calibrated reliability.
5. A small-model reply that is repetitive, empty, or fails to answer needs a
   separate bounded quality check/retry. Changing the memory route alone does
   not fix robot identity knowledge or general-answer quality.

## Implementation sequence

1. Add the semantic contract and strict parser beside the historical Boolean
   contract. Exercise all modes and invalid outputs with controlled backends.
2. Implement route-independent history authorization and test deliberate
   false-negative routes after correction/deletion/expiry, before weakening
   existing recall protections.
3. Implement answerability-aware behavior for optional, required, mixed and
   unresolved requests. Preserve evidence checks and raw output provenance.
4. Integrate the contract with the CLI, both routing adapters, instrumentation,
   and evaluation readers. Historical artifacts must remain interpretable and
   retain their original results. Expose the effective mode in diagnostics.
5. Evaluate a candidate policy against the current policy on a newly frozen,
   independently labeled set. Use the current diagnostic only for development.
   Promote the new default only after reviewing quality and latency together.

Primary affected modules: `routing.py`, `conversation.py`,
`lightweight_routing.py`, `evaluation_systems.py`, `cli.py`, and the evaluation
schema/parser consumers. Preserve the existing retrieval/store authorization
checks rather than delegating them to a model.

## Acceptance checks

- Score false required-memory routes on general/current-input questions
  separately from missed required-memory routes on personal recall.
- Assess mixed and ambiguous cases by whether the delivered answer or
  clarification addresses the task; a forced binary label is insufficient.
- Include paraphrases, speech-like punctuation, fully supplied personal
  constraints, technical help, social advice, topic changes and follow-ups.
- Test empty, irrelevant, conflicting, corrected, deleted and expired records.
  Inject deliberately wrong routing decisions into lifecycle tests.
- Preserve ordinary multi-turn editing/explanation while preventing old
  personal values from bypassing record authorization through dialogue history.
- Test incomplete speech and repetitive/vague small-model answers separately
  from routing correctness.
- Record answer quality, clarification frequency, model switches, extra review
  calls and latency. Distinguish cold and warm runs and text-only replay from
  live speech-to-response timing.
- Require zero authorization violations and zero incorrect memory refusals in
  the agreed release suite, while reporting the suite size and limits. Passing
  a finite suite cannot guarantee error-free conversation on every future input.

The next release decision should be based on these measured behaviors, not a
larger number of phrase exceptions or an increased unit-test count alone.
