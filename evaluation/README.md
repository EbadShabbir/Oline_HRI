# Fictional seven-day evaluation suite

`fictional_seven_day_v1.json` is a controlled, fully synthetic personal-memory
case study. Mira, Theo, Luma, and every event are invented. The suite contains
no human-participant data and must not be described as a user study.

The manifest fixes one UTC week, Monday 3 August through Sunday 9 August 2026.
All cases are evaluated at `2026-08-09T20:00:00.000000Z`, after every event has
been replayed. Version 1 contains:

- 15 ordered lifecycle events: 13 remembers, one correction, and one forget;
- 14 deterministic `mem_` record versions;
- three withheld topic categories whose private values are not present; and
- 30 author-gold prompts covering all four memory/model routes.

The route distribution is seven small/no-memory, seven large/no-memory, twelve
small/memory, and four large/memory cases. The memory cases cover direct facts,
a changed preference, an expired event, a hard-deleted competing plan, an
unresolved contradiction, genuine older-versus-newer event selection, temporal
reasoning, absent information, confirmed sensitive information, prohibited
secrets, unconfirmed third-party data, and unconfirmed affect inference.

## Replay contract

Replay `memory_events` in manifest order with a clock fixed to each event's
canonical UTC `timestamp`. A public replay helper may inject each record's
deterministic ID through `MemoryStore.memory_id_factory`; these IDs are test
identifiers, not production IDs.

The replay destination must be an absolute, previously unused file path inside
an existing owner-only directory with no symlink components or untrusted
writable ancestors. The helper rejects pre-existing SQLite sidecars, checks the
database file identity throughout replay, and removes the owned database after
a failed invocation only when its identity is still exact and no ambiguous
sidecars remain.

- `remember` creates the exact full `record`.
- `correct` supersedes `target_id` and creates the exact replacement `record`.
- `forget` hard-deletes `target_id` and its revision ancestors.

After replay, `mem_00000000000000000000000000000002` is superseded,
`mem_00000000000000000000000000000006` is expired, and
`mem_0000000000000000000000000000000a` has been deleted. The conflicting Lab A
and Lab B records remain active deliberately so the robot must express
uncertainty rather than choose one.

`withheld_topics` records only a category and policy explanation. It never
contains a PIN, third-party address, inferred affect value, placeholder secret,
or corresponding memory ID. Do not add such values when extending the suite.

## Gold annotations

Each case contains an independent expected route, retrieval gold, and a
natural-language answer rubric:

- `relevant_ids` contains every record that truly bears on the prompt.
- `required_ids` is the subset that a complete supported answer must use.
- `forbidden_ids` contains stale, expired, superseded, or deleted records that
  must not ground the answer.
- `top_id` is the expected first relevant result, or `null` when no answer
  exists or equally authoritative records conflict.
- `required_citation_ids` lists the exact IDs a supported or uncertainty answer
  must cite.

These are evaluator-authored gold labels, not the runtime's hidden
request-link decision. Manifest validation requires `required_ids` and
`required_citation_ids` to be equal, and the runner keeps both fields and all
other gold data out of model and production-router inputs. At runtime,
`Conversation` derives required evidence independently with conservative
best-effort heuristics; disagreement with the gold remains an evaluation result,
not a reason to expose or rewrite the labels.

An absent-information case intentionally has empty gold even if an imperfect
retriever returns a nearest but irrelevant record. Do not change empty gold or
invent a citation to accommodate runtime behavior. That distinction is needed
for later evaluation of abstention and false retrieval.

Each emitted JSON line is an evaluator-side record, not a model message. A
runner must send only the `prompt` value to the system under test and
keep `expected_route`, retrieval gold, and answer rubrics hidden until scoring.
The Step 16 runner enforces that separation through its execution-case view.

The annotation status is `author_gold_pending_independent_review`. A second
reviewer should check the prompts and labels without seeing model outputs before
the suite is used for reported results. This manifest contains no model output,
measurements, scores, pass rates, latency, resource use, or Step 16 results.

## Historical Step 16 run and merge (pre-redesign)

The following results are historical, pre-redesign Step 16 measurements from
2026-09-07. The four-baseline collection and objective merge completed: all 120
turns produced valid structured output with no errors or fallbacks. All four source
bundles passed the common-provenance checks. The aggregate historical results
are summarized in the
[project README](../README.md#historical-step-16-objective-evaluation-pre-redesign).
Raw dated bundles, generated reports, and the supplementary router-only bundle
contain prompts, answers, provenance, and device telemetry. They are intentionally
ignored, kept local, and not versioned; the router-only results also remain
separate from the adaptive results. An earlier run was interrupted by an
unclean reboot, whose trigger remains unknown. Full Step 16 interpretation is
still provisional pending independent label and answer review and the deferred
deployment measurements. They must be rerun before being attributed to the
current routing and grounded-generation implementation. Current post-redesign
unit and live-regression results are recorded in the
[project README](../README.md#post-fix-validation).

Settings and scoring rules are fixed in
[the Step 16 protocol](step16_protocol.md): temperature 0, seed 42,
2,048-token context, 256-token output cap, non-thinking mode, and one stateless
turn per case and strategy. Each bundle also runs the independent top-five
retrieval pass over the 16 memory cases. The retained bundles reflect the
pre-redesign evidence contract and must not be reinterpreted using current
validation semantics. In a current rerun, production diagnostics distinguish raw
ranked retrieval candidates, the whole evidence actually supplied to
generation, and the model's validated citations. The current deterministic,
best-effort request-link analysis is independent of model size. Direct recall
uses the best-supported high-confidence linked evidence, while explicit
multi-memory wording may supply up to three candidates. Required records are
packed first; optional tail records may be pruned, but all required records must
fit or the turn fails before generation. A semantic-only candidate without a
detectable lexical, name/label, preference, or temporal link causes a
conservative abstention. This is not a calibrated semantic-relevance guarantee.

For a grounded answer, every runtime-required evidence ID must be cited and its
high-confidence literal anchors covered in speech. Optional supplied candidates
cannot be cited. With no high-confidence request link, the application discards
model prose and emits a fixed abstention. An empty citation list is also replaced
with that fixed response; if evidence was linked, the subsequent required-citation
gate rejects it. Other incomplete citations cannot authorize a linked answer.
Memory IDs are forbidden in speech itself.
Model-facing records rewrite bare `User` and `the user` forms to `you`/`your`.
Human facts must use `you`/`your`, never literal `the user` or robot `I`/`my`.
Best-effort validators check cited-record completeness and requested temporal
details; reject detectable perspective swaps, unsupported names and personal
relationships, unsupported temporal precision, and preference/relationship
polarity reversals, including temporal-preference negation; and enforce a cited
exactly-three-step preference. A narrow short-label conflict check requires
uncertainty. The complex-general/no-memory
rule used by the current architecture regression caps speech at 75 words,
compares exactly three architectures, gives one recommendation, and requires
exactly three short deployment steps.

These checks are literal and heuristic. They do not prove general semantic
completeness, contradiction handling, or temporal correctness, and conservative
abstention can reject a truly relevant semantic-only match. They supplement but
do not replace blinded semantic review.

The following recipe reproduces a full collection in a fresh directory. Avoid
competing inference clients. Run from the repository root with the local
Ollama models and pinned BGE assets installed. Use a fresh private directory
on persistent storage. An
earlier collection stored under `/tmp` disappeared when the Jetson rebooted;
those lost artifacts cannot support a final report.

```bash
: "${OLINE_HRI_RUN_ROOT:?set it to an existing private persistent directory}"
RUN_DIR=$(mktemp -d "$OLINE_HRI_RUN_ROOT/oline-hri-step16.XXXXXX")
printf '%s\n' "$RUN_DIR"
for STRATEGY in always_small_no_rag always_large_no_rag always_large_with_rag adaptive; do
  mkdir -m 700 "$RUN_DIR/$STRATEGY"
  ollama stop qwen3:0.6b
  ollama stop qwen3:4b
  ollama ps
  PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation_benchmark run \
    --output-dir "$RUN_DIR/$STRATEGY" \
    --block-device mmcblk0 \
    --strategy "$STRATEGY" \
    --telemetry-interval-ms 500 || break
done
```

Keep the printed `RUN_DIR` path so the results can be found after reconnecting.
The order above is frozen, and Ollama must have no resident model before each
bundle; avoid other inference clients during collection. Cold 4B generations
can make the complete comparison take several hours. A completed bundle may
contain failed individual cases: timeouts and invalid responses remain in the
scoring denominator. If the process is interrupted, preserve its incomplete
bundle and use a fresh directory for a replacement run. The tools never
overwrite existing artifacts.

After all four bundles complete, merge them offline:

```bash
mkdir -m 700 "$RUN_DIR/merged"
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation_merge merge \
  --bundle-dir "$RUN_DIR/always_small_no_rag" \
  --bundle-dir "$RUN_DIR/always_large_no_rag" \
  --bundle-dir "$RUN_DIR/always_large_with_rag" \
  --bundle-dir "$RUN_DIR/adaptive" \
  --output-dir "$RUN_DIR/merged"
```

Each source bundle contains mode-0600 `observations.jsonl`, `environment.json`,
`telemetry.jsonl`, `telemetry_summary.json`, `summary.json`, `report.md`, and
`answer_review.jsonl`. Output directories must already exist with mode 0700
and be absolute, owner-controlled, and symlink-free. Raw observations are
written incrementally; derived artifacts are published after collection
finishes. Progress output contains case IDs and status, not prompts or answers.

The merger requires four complete, distinct strategies with matching suite,
configuration, runtime source, models, embedding assets, and device/software
provenance. It selects component retrieval from `always_small_no_rag` as
specified before execution. It writes the combined objective `summary.json`,
`report.md`, 120-row `answer_review.jsonl`, and an artifact-hash `manifest.json`
without changing source bundles. Telemetry remains in each source bundle;
whole-run energy includes setup and component retrieval and is not attributed
to individual answers.

Automated scores cover routing, retrieval Recall@5/MRR, supplied-memory
precision, required/forbidden IDs, citation IDs, structural validity, failures,
fallbacks, and observed stage latencies. They do not establish whether the
free-text speech satisfies its answer rubric. Accuracy, temporal reasoning,
updated-preference answers, abstention, uncertainty, and hallucination require
blinded human review. Their status remains
`pending_blinded_human_review` with `reportable: false`; label review is also
still pending.

The current development device uses 15W mode and `/dev/mmcblk0` SD storage,
with GUI and development processes active. Its storage counters are not NVMe
measurements, and one repetition in a fixed order cannot isolate thermal,
cache, or background-process effects. Microphone/STT, speaker/TTS, gestures,
actuation, final-NVMe operation, and physical offline-disconnection tests remain
deferred. The text path uses loopback Ollama and authenticated local embedding
assets; no network-disconnection claim follows from that configuration alone.

### Router-only supplement

The [supplementary protocol](step16_router_only_protocol.md) evaluates only the
production Qwen3-0.6B router. It records decisions, monotonic latency, and Ollama
token metadata for all 30 stateless cases. A backend guard rejects answer
generation and 4B inference, even when a route selects `large`. Failures and
missing cases remain in the accuracy denominator. This cannot establish
adaptive answer quality or compute savings and must not be merged as an
adaptive baseline.

To repeat this small-only evaluation in a new private output directory:

```bash
: "${OLINE_HRI_RUN_ROOT:?set it to an existing private persistent directory}"
ROUTER_DIR=$(mktemp -d "$OLINE_HRI_RUN_ROOT/oline-hri-router.XXXXXX")
ollama stop qwen3:0.6b
ollama ps
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation_router \
  --output-dir "$ROUTER_DIR"
```

The command writes mode-0600 `observations.jsonl` and `summary.json` without
overwriting existing artifacts. The retained run also has a separately captured
`environment_before.json`; the router command does not itself collect hardware
telemetry or that environment sidecar. It includes suite, configuration,
router-source, and router-system-prompt hashes in its observations header.
