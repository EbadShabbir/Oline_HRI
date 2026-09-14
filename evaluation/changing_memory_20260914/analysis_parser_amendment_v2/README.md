# Separate analysis amendment: supplied-evidence extraction

This post-collection analysis amendment was prepared on 14 September 2026 after
the cm01–cm04 branches and their original A/B assistant judgments were sealed,
while later live branches continued. It changes diagnostic parsing only. It
does not change the frozen runtime, experiment schedule, expected-state ledger,
rubrics, delivered answers, public review packets, grouping, vote validation,
adjudication or answer-quality metrics. No model inference or experimental rerun
was performed for this amendment. Assistant review; human validation pending.

The original approved analyzer remains at
[`scripts/analyze_changing_memory.py`](../../../scripts/analyze_changing_memory.py)
and is preserved here as [analyzer_v1.py](analyzer_v1.py). Its SHA256 is
`60709a1002f7537f8cfd8ea57e8c89052f7ba2e608ca4b36e275a0fc79c95215`.
The separate executable is
[`scripts/analyze_changing_memory_v2.py`](../../../scripts/analyze_changing_memory_v2.py),
also copied here as [analyzer_v2.py](analyzer_v2.py), SHA256
`65181ee60ac1064ac00fd27d956236d92bac343829cb0f56263bd2dd55297e00`.

## Why the amendment is necessary

The frozen runner extracts the convenience field
`supplied_evidence_envelopes` only when a message starts with
`PERSONAL_MEMORY_DATA=`. Production generation requests put explanatory prose
before that envelope. A rejected conversation also lacks the returned
`supplied_records` field, even though the actual input messages remain preserved
in call and trace records. The original analyzer therefore could diagnose
missing supplied evidence when the generator demonstrably received it.

The concrete case is `cm04_correction_restart_fresh`. Its current Niko Fern
record was supplied and cited; the collaborator validator rejected the answer.
The original analyzer reports both `evidence_selection_required_fact_missing`
and `validation_rejection`. The amendment recovers the recorded evidence and
reports only `validation_rejection`. See the
[diagnostic examples](../diagnostic_examples_v1.md) for the question, raw speech,
actual envelope, freshness checks and validator source. This parser does not
itself decide whether withholding was necessary; that conclusion requires
inspection of the supported raw answer and validator behavior.

## Narrow implementation

The v2 file is a copy of v1 with one import, one new helper and one call extending
the supplied-record list inside `diagnostics`. The helper reads only final user
messages from recorded generation calls and `answer_generation` request spans.
It does not use classifier prompts, earlier conversation messages, raw answers
or the expected ledger as evidence. It accepts the production envelope after a
prose prefix, requires a standalone `PERSONAL_MEMORY_DATA=` marker, and parses
the JSON envelope before the `CURRENT_USER_REQUEST` suffix. Direct envelope-only
messages remain supported.

Malformed JSON, duplicate JSON keys, non-JSON constants, malformed record
identities/text, multiple envelopes, unexpected trailing content, repeated IDs
within an envelope, and conflicting records for one ID across generation
requests raise an analysis error. They cannot silently become evidence absence.
Identical call/trace copies are deduplicated. IDs and canonical text remain
exactly as recorded; no memory selector or fact is reconstructed from an answer.
The original convenience fields remain available and unchanged.

## Validation and independent review

Run from the repository root:

```sh
.venv/bin/python -m unittest tests.test_analysis_memory_evidence_v2 tests.test_analysis_changing_memory -v
```

The final run passed **16 tests in 2.104 seconds**: seven amendment tests plus
nine original analyzer tests. [attempt_02.json](attempt_02.json) records the
command, source hashes and return code; [attempt_02.log](attempt_02.log) contains
the output. The new tests are preserved as
[test_analysis_memory_evidence_v2.py](test_analysis_memory_evidence_v2.py).
An initial test run passed 15 tests and failed one final assertion because the
new test used the wrong existing resolved-vote filename. Only that assertion
path was corrected; [attempt_01.json](attempt_01.json) preserves the failure.
This was an offline test error, not an experimental checkpoint or runtime repair.

The tests establish that the amended syntax tree equals the original after
removing the new helper/import and its one diagnostic call. A full synthetic
288-checkpoint comparison produces byte-identical public packets, review schema,
group mapping and resolved votes. All non-diagnostic reviewed-answer fields and
all metrics other than stage-finding counts remain identical. Only the one
fabricated prefixed withheld-answer fixture changes diagnosis. Additional tests
cover malformed inputs, ID preservation, duplicate call/trace copies and
exclusion of history/classifier/answer content.

A read-only parser check covered the 96 scored rows of the already sealed
cm01–cm04 branches, found 34 rows with actual generation evidence, and encountered
no malformed or ambiguous envelope. It recovered the current Niko record ID in
the rejected-response case. The exact checked input hashes and v1/v2 diagnosis
are in [sealed_cm01_cm04_parser_check.json](sealed_cm01_cm04_parser_check.json).
These are parser coverage counts, not answer-quality scores; no later branch
answers were read for this check.

The independent root assistant reviewed the diff and regressions and approved
this separate amendment before sealing. Its approval is recorded in
[provenance.json](provenance.json). The root will resolve both analyzers against
the same final sealed review judgments, retain both outputs, and compare all
non-diagnostic fields exactly. Final command lines and source hashes belong in
each analysis output's own provenance. The final report should label v2 stage
diagnoses as amended analysis and retain the original v1 findings. The frozen
experiment's answer observations and assistant judgments are unchanged.
