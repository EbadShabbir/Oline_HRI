# Blinded semantic answer review

These instructions apply to the existing frozen workload rubrics. They do not
introduce a new acceptance threshold, alter a rubric, or change the experiment.
Use two independent assistant contexts and resolve disagreements in a third
blinded context before unblinding. Independent human validation remains pending.

## Packet generation and separation

After collection, generate the packet with the frozen analyzer and a new output
directory. This performs offline analysis only:

```bash
PYTHONPATH=scripts .venv/bin/python scripts/analyze_routing_overhead.py blind \
  --run-root evaluation/routing_overhead_20260912/run_v1 \
  --workload evaluation/routing_overhead_20260912/frozen_v1/workload.json \
  --freeze evaluation/routing_overhead_20260912/frozen_v1/freeze.json \
  --output-dir evaluation/routing_overhead_20260912/blind_v1
```

`packet.jsonl` contains randomized anonymous answer IDs and these fields:

| Field | Meaning |
| --- | --- |
| `answer_id` | Anonymous review group identifier; copy exactly |
| `question` | Current user utterance |
| `history` | Exact retained prior messages used for this answer |
| `rubric` | Frozen required claims, forbidden claims and reference criteria |
| `prepared_memory` | Fictional memory setup operations in chronological order |
| `answer` | Delivered answer text; an empty string when nothing was delivered |
| `response_complete` | Whether the system delivered a validated response |
| `answer_constraint` | Shared authored helper constraint, when used |

An output group merges only identical question, history, rubric, prepared memory,
answer, delivery status and constraint. Repetition or model identity is never a
grouping assumption. Packet entries contain no model, arm, timing or workload ID.

`private_mapping.json` joins answers back to raw attempts. Reviewers must not
read that file, raw collection records, timing reports, other reviewers' answers
or any file outside the packet/cohort paths they are assigned. Start reviewers
with fresh conversation context and no copied experiment results.

For manageable review, split the randomized packet into consecutive cohorts of
approximately 12–20 groups. Preserve each entry byte-for-byte or preserve its
parsed JSON exactly. Retain the complete packet, cohort membership and SHA-256
hashes. Each reviewer assesses every cohort independently. A shared fictional
memory seed may be printed once when inspecting a cohort, but must remain
available to both reviewers. Never drop failed deliveries or difficult answers.

## Reviewer task

Judge the **delivered current answer** against its exact frozen rubric, using
the current question, retained history and prepared memory as context. Consider
all required claims and explicit constraints. Do not reward fluent language,
valid JSON, matching keywords or appropriate tone as substitutes for correctness.
Do not silently strengthen or relax a rubric after reading an answer.

Distinguish factual support from mere mention. A negated claim does not satisfy
a requirement to assert it. Prior assistant text is not automatically reliable
evidence. Apply corrections, expiry, forgetting and unresolved conflicts in the
prepared memory when relevant. Do not require memory use for a general/social
question. Shared authored answer helpers may produce a correct answer; score
the delivered answer without attributing that result to independent reasoning.

Choose exactly one label:

| Label | Definition |
| --- | --- |
| `complete` | Every required semantic claim and explicit constraint is satisfied, with no material false or unsupported claim |
| `appropriate_abstention` | The rubric calls for abstention because the answer is unknown, and the response correctly avoids inventing it |
| `appropriate_uncertainty` | The rubric calls for acknowledging unresolved uncertainty/conflict or requesting clarification, and the response does so completely |
| `partial` | Some relevant requirements are satisfied, but a required claim/constraint is missing or incomplete |
| `incorrect` | The central answer is wrong, contradicts the rubric/evidence, or invents the answer |
| `inappropriate_abstention` | The answer declines, claims ignorance or requests unnecessary clarification although the rubric supplies an answerable task |
| `technical_failure` | `response_complete` is false; no complete validated answer was delivered |

Use `partial` only when it describes the missing requirements better than a
wrong central answer. If several labels seem plausible, explain the decisive
rubric issue in the rationale; an adjudicator will resolve disagreements.
Abstention or uncertainty counts as correct only when required by that rubric.
Never label an undelivered answer correct. The three correct labels must not
carry an unsupported-claim flag.

Return one JSON object per assigned `answer_id`, in JSON Lines format:

```json
{"answer_id":"COPY_EXACT_ID","label":"complete","unsupported_claim":false,"unsupported_personal_claim":false,"rationale":"Explains why each material rubric requirement is met, or identifies the specific missing, false or unsupported claim."}
```

Both flags must be booleans. `unsupported_claim` marks a material unsupported
factual assertion; `unsupported_personal_claim` marks the subset about the
human's facts/preferences/history. A harmless social expression is not an
unsupported factual assertion. Keep rationales concise but specific enough to
audit the judgment. Do not include model guesses, arm names, timings or scores
from other answers. Do not add observations outside the assigned cohort.

## Agreement and adjudication

Retain reviewer A and reviewer B files unchanged. Verify complete, unique
coverage of all anonymous IDs and recognized labels. Compare the label and both
flags, retaining the rationales. Report initial agreement using all unique
review groups, not the number of repeated model requests.

For every disagreement, give an independent third context the original blinded
packet entry and the two anonymous judgments, with no mapping/timing/model
information. Require a final label, flags and rationale. Retain the adjudication
and the disagreement list. Agreement is not proof of correctness; a documented
blinded audit can identify a shared substantive error, which must be retained
as an explicit correction rather than silently changing original reviews.

Write a resolved JSONL file with exactly one final judgment for every packet ID.
Only then unblind and join results:

```bash
MPLCONFIGDIR=/tmp/clara-routing-mpl /tmp/clara-step4-plots/bin/python \
  scripts/analyze_routing_overhead.py analyze \
  --run-root evaluation/routing_overhead_20260912/run_v1 \
  --workload evaluation/routing_overhead_20260912/frozen_v1/workload.json \
  --freeze evaluation/routing_overhead_20260912/frozen_v1/freeze.json \
  --blind-dir evaluation/routing_overhead_20260912/blind_v1 \
  --reviews evaluation/routing_overhead_20260912/reviews_v1/resolved.jsonl \
  --output-dir evaluation/routing_overhead_20260912/analysis_reviewed_v1
```

The analyzer rejects missing/duplicate IDs, unblinded fields, recognized-correct
labels on failed deliveries, unsupported-claim contradictions and mismatched
question/history/answer content. It reports the three correct labels separately
from validation success and retains every attempt in the quality denominator.
Repeated answers, turns in a sequence, shared templates and the shared fictional
profile are dependent. Review counts do not create independent task samples or
establish a population-level quality–latency improvement.
