# Independent methods audit notes

Prepared 14 September 2026 by the independent integrity-audit assistant
`/root/runtime_audit` for the final report writer. This document describes the
frozen method and its limits. It contains no live outcome judgments or claims
that planned checkpoints completed. No live answer or collection files were
read for this task. **Assistant methods review; human validation pending.**

The primary sources are the [frozen protocol](frozen_v1/protocol.md),
[runtime schedule](frozen_v1/runtime.json), [expected-state ledger](frozen_v1/expected_ledger.json),
[configuration and environment freeze](frozen_v1/freeze.json),
[frozen runner](frozen_v1/source/scripts/run_changing_memory.py), and
[independent pre-inference review](frozen_v1/preflight_review.json). The final
report must use the sealed collection and blinded answer judgments to establish
what actually happened. Source inspection alone establishes intended mechanisms.

## Runtime and deployment choice

The experiment freezes the CLI-default `llm` routing policy:
`ConversationRouter` performs the ordinary small-model memory and compute
classifications, followed by production overrides. `LightweightRouter` remains
an opt-in policy; its use in a recent completed routing-overhead experiment did
not change the CLI default. The deployed conversation helpers, evidence
selection, grounded composition, answer constraints, transformations, validation
and fallback behavior remain enabled. Consequently a nominal route is not
sufficient evidence of which model generated an answer. Report recorded calls
and generation policy alongside the requested route. This is a test of the
delivered adaptive system, not an isolated language-model capability comparison.

The resolved schema-7 configuration uses the installed `qwen3:0.6b` and
`qwen3:1.7b` tags, 2,048 context tokens, a 192-token output budget, temperature
zero, and thinking disabled. The runner fixes generation seed 42. The small and
large request timeouts are 60 and 120 seconds; unload timeout is 30 seconds.
The ordinary Ollama client uses `retain_large_model=False`. Model digests, the
reported Ollama version (0.33.3), Python and package versions, embedding asset
hashes, device policy and 41 source-file hashes are frozen. The model tags are
deployment identifiers; detailed model metadata is retained in `freeze.json`.

Embeddings use the installed `BAAI/bge-small-en-v1.5` assets at revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, through the production ONNX CPU path
with two intra-operation threads and normalized 384-dimensional vectors. Both
storage passage embeddings and retrieval query embeddings use this real path;
query instruction handling remains unchanged. No simulated model or embedding
output qualifies as a live checkpoint. Each worker checks the frozen runtime
before collection; model inventory and environment checks must not be confused
with a guarantee of identical generated text on every future run.

## Authored states, branches and expectations

Twelve independent fictional scenarios cover three preferences, two
relationships, three object locations, two appointments and two dated events.
Each scenario creates three separate new persistent SQLite databases for
correction, deletion and expiry. Each branch begins with the same authored
subject fact and a separate historical-control event. Their mutations and
database files are independent. In particular, expiry branches do not delete or
correct their records.

The schedule contains 288 scored checkpoints: 120 correction, 84 deletion and
84 expiry. Expected response categories are 48 original recalls, 48 replacement
recalls, 48 historical-control recalls and 144 appropriate-uncertainty answers.
There are 180 retained-history questions, 108 fresh-history questions, 108 matched
retained/fresh pairs and 108 questions after a scheduled process restart. These
are planned denominators. There are 12 independent authored units, not 288
independent estimates of general household reliability.

The [standalone authoring program](frozen_v1/preparation/author_ledger.py) derives
authorized states and rubrics from authored events. It imports no production
eligibility implementation and reads no database, retrieval result or generated
answer. The independent pre-inference reviewer separately replayed all 288
expected states and checked their time, branch, question, eligibility, permitted
evidence and forbidden values. A failed runtime write does not change the
authored expectation. The runner receives the operation schedule, facts needed
for explicit storage operations, and questions. Expected answers, forbidden
values and rubrics are not supplied as model or embedding inputs. Reading their
hashes for freeze verification does not expose their contents to inference.

Authored v1 is preserved. The documented [v2 authoring changes](frozen_v1/preparation/authoring_v2_changes.md)
changed the 36 original disclosure turns to plain first-person facts and
corrected confirmation/cache wording before inference. The 288 expected ledger
entries remained byte-identical. Mutable appointments and dated subject facts
use canonical text with `event_time=None`, because the real correction API
preserves that optional field. Historical controls have explicit event times.
This prospective representation choice limits claims about correction of
structured event-time metadata.

## Storage, confirmation and controlled expiry

The original subject first enters a real retained `Conversation.send` turn.
Its delivered acknowledgment and committed history are recorded. Explicit
remember, correction and forget instructions then pass through the actual
public memory CLI handler, `_run_memory`, on the same live `MemoryStore`.
`remember` writes a confirmed record with the real embedding path; `correct`
supersedes the old record and creates its replacement; `forget` removes the
target and superseded ancestors through the real API. Read-only database
snapshots and API acknowledgments allow later comparison of intended and
committed state.

Here, confirmation means the authored evaluation instruction authorizes the
confirmed-write API. The API output and `consent_status="confirmed"` document
that operation. The earlier conversational acknowledgment is neither evidence
of user consent by itself nor proof that storage succeeded. This does not test
an interactive model-generated read-back/yes-no confirmation dialogue or
automatic memory capture.

One explicit, timezone-aware, monotonically advancing `EvaluationClock` is
injected into `MemoryStore`. It governs storage timestamps, eligibility in
lexical and semantic retrieval, actual retention purge, and snapshot validation
delegated back to the store. The clock stays fixed throughout each inference
and advances only between scheduled operations. Wall-clock durations are
recorded separately. The operating-system clock and stored rows are not edited
to manufacture expiry.

The deployed seven-day retention setting is used without shortening it. Records
stored at logical `2026-10-01T12:00:00+00:00` expire at
`2026-10-08T12:00:00+00:00`. A record is eligible only while its retention
deadline is strictly later than the evaluation time. Queries run one microsecond
before the boundary, exactly at it, one microsecond after it, and two seconds
after it following process restart. Equality requires exclusion. Correction
occurs one minute after storage and preserves the original retention deadline.
Both the subject and historical control expire in the expiry branch. Production
purge operations are observed rather than replaced with diagnostic SQL writes.
Describe these results as **controlled logical-time expiry**, not seven days of
wall-clock aging.

## Retained history and actual stale-state exposure

Within each process, one live conversation persists across mutation. Production
history remains bounded and subject to ordinary routing and commit rules.
Memory-request turns are not appended as reusable history; non-memory turns can
be appended. A disclosure may be classified or rejected in a way that prevents
the original user statement from remaining in the stored conversation. No
fictitious acknowledgment is inserted to compensate.

Post-change questions explicitly refer to an earlier statement, allowing the
production prior-turn gate to forward retained history. This wording contains
neither the old nor replacement answer. Fresh-history probes create a separate
empty conversation sharing the backend, router, store and retriever; they do
not replace the retained conversation or reset Ollama/BGE. The identical
question within each retained/fresh pair supports a descriptive paired
comparison. The first post-correction phrasing is an unseen paraphrase; repeated
pair or restart wording must not be presented as independent paraphrase trials.

The final trace audit should distinguish the exact original user statement
remaining in history from its actual inclusion in a generation request.
It should also count literal original-value exposure, including later assistant
echoes after bounded history has pruned the original statement. To establish
history forwarding, intersect stored history with actual generation messages,
excluding system messages, the current request and the supplied memory-evidence
tail. Literal matching is a lower bound on witnessed exposure. Absence of a
literal match does not establish semantic absence: time aliases and paraphrases
can differ. Exposure is also not an answer-correctness judgment or authorization
to disclose a revoked fact.

## Retrieval state and process restart

The production retriever has no persistent vector-result cache. Real repeated
lexical/semantic/hybrid probes warm normal runtime state; semantic retrieval
reloads eligible records and rebuilds its embedding matrix. BGE and Ollama are
warmed through ordinary calls. The harness also captures actual original
`HybridMatch` results as an evaluation-owned stale snapshot and later calls
the real `is_current` validation API on them.

The runner contains a snapshot-injection hook for an offline stale-result
regression test. The live schedule never activates that hook. Live snapshot
probes check the captured snapshot's freshness; subsequent answer retrieval
continues through the production retriever. Thus the experiment exercises stale
snapshot validation and retained conversation state, but does not measure live
generation under an artificially substituted stale retrieval result. A correct
snapshot decision alone does not establish a correct delivered answer.

Each branch has a scheduled worker exit followed by a distinct operating-system
process that reopens the same persistent database. The method records PID,
parent PID, boot identity, Linux process-start ticks, and database
path/device/inode. Recreating a Python object in the same process is rejected.
The evaluation serializes the actual retained history, logical clock, record
identifiers and captured snapshot, then explicitly restores them in the new
worker. This restoration deliberately stresses stale conversation/snapshot
state; it does not establish that ordinary deployment automatically persists
conversation history. Fresh-history restart probes also use the reopened
database. The Ollama server and operating system are not restarted.

## Guards, interruption handling and evidence

Inference is serialized under inherited exclusive leases for the common Jetson,
independent-retrieval and matched-evidence experiments. Workers validate lease
file identity; known competing experiments are checked. The frozen
`post_memory_existing_swap_reserve_v2` policy requires at least 2 GiB available
RAM and temperature below 55 C for admission, then at least 768 MiB available
RAM and temperature below 68 C during execution. It reserves 256 MiB of the
existing 3,901,608 KiB logical swap capacity, giving a 3,639,464 KiB usage
ceiling. This is the existing experiment admission policy, not a validated
physical safety threshold.

The policy also requires 15 W mode 0, active fan, unchanged boot and thermal-trip
counters, unchanged swap capacity, at most one resident model, 500 ms telemetry
and a five-second telemetry-stall ceiling. Only the owned 0.6B/1.7B pair is used;
the retired 4B model is excluded. Peer eviction and large-model cleanup remain
part of the execution. Final resource capture fails closed. The method makes
no persistent operating-system, power or swap configuration changes.

Actual state is saved after every attempted operation. A failed or interrupted
checkpoint remains failed. A separately identified continuation may execute
only the exact unattempted suffix after the unchanged guards pass. It must not
repeat an attempted checkpoint, invent a successful acknowledgment, or blindly
replay an ambiguous mutation. Scheduled restart and recovery-worker restarts
must be reported separately. Supervisor interruption stops and reaps the child
under the lease, attempts owned-model cleanup, and preserves a stop artifact.
Exclusive paths, hashes and read-only seals protect artifact integrity against
accidental alteration; they are not privileged tamper-proof storage.

Instrumentation preserves operation/checkpoint identities, API outputs,
logical times, process/database identities, actual committed/forwarded history,
retrieved records, supplied evidence envelopes, snapshot decisions, model calls,
received HTTP bytes, raw model output, delivered answer, validation outcomes,
exceptions and resource observations. This permits stage-aware diagnosis:
storage failure differs from routing that skipped retrieval, retrieval that
returned unsuitable evidence, generation that ignored suitable evidence, and
validation that withheld a response. A generation-stage failure should not be
assigned when generation was never reached. A validation rejection is not by
itself proof of a validator defect.

## Offline validation, review and reporting limits

The final frozen harness suite passed **14 offline tests in 20.114 seconds**;
the [command and hashes](frozen_v1/preparation/offline_validation/attempt_02.json)
and [test output](frozen_v1/preparation/offline_validation/attempt_02.log) are
preserved. From the repository root, its recorded command is:

```sh
.venv/bin/python -m unittest tests.test_changing_memory -v
```

Coverage includes the authored schema, actual CLI mutations, exact expiry
boundary, fresh/retained history isolation, supplied evidence, stale-snapshot
rejection, interrupted generation, actual worker-process restart, database and
clock checks, durable suffix continuation, source/config drift, inherited
leases, missing final snapshots and supervisor interruption cleanup. Synthetic
inference in these tests validates the harness and contributes zero live
checkpoint observations.

The prospective answer review supplies two independent blinded assistants only
the question, authorized state, rubric and delivered answer. Model/route,
retrieval, raw answer, validation and timing diagnostics remain hidden until
judgments are frozen. Exact duplicate packets may be grouped with a complete
binding map. A third blinded assistant adjudicates disagreements before
diagnostic unblinding. The final report must establish that this sequence
actually occurred and retain the original votes and disagreement records.
All such judgments remain **assistant review; human validation pending**.

A useful correct delivered answer and safe withholding are different outcomes.
Withholding, technical failure or missing output never counts as successful
recall; uncertainty is appropriate only when the authored state makes the fact
unavailable. Giving the replacement together with an unrequested old value is
still stale disclosure. Legitimate historical questions in the correction
branch ask about a separate confirmed historical control. Questions asking
for the forgotten subject's former statement still require nondisclosure;
historical phrasing does not undo the frozen forgetting policy.

Final claims should cover these fictional text episodes, actual conversation
worker restart and controlled expiry. They do not establish power-loss recovery,
OS-reboot recovery, durability under abrupt hardware failure, spoken/STT/TTS
performance, long-term wall-clock aging, a population reliability rate, or an
advantage of learned routing. Unfavorable outcomes and missing checkpoints must
remain visible. Any later repair and rerun require separate labels and cannot
replace this frozen experiment's observations.
