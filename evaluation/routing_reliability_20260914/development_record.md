# Dependency classifier development record

These are development observations, not independent release accuracy.
The original 24-case diagnostic became development data when its failures
were inspected. Historical artifacts remain unchanged.

The initial Boolean router incorrectly required personal memory on 5 of 12
general questions and missed 1 of 8 required-recall questions. Three subsequent
Qwen semantic-prompt experiments did not make dependency classification
reliable. Their complete model calls and failures are preserved under
`tmp/semantic_dev_routing_v1`, `v2`, and `v3`, with additional bounded model
probes under `tmp/dependency_mode_probe_*` and `tmp/dependency_reason_probe_v1`.
The Qwen semantic adapter remains available for reproduction; it is not the
selected dependency classifier.

The first local classifier used 200 authored examples: 160 training and 40
calibration, with disjoint groups. Despite 37/40 raw calibration matches, it
failed the known development questions: only 5/12 general cases received
`none`, five clarified and two incorrectly required recall. Its raw scores,
rejection thresholds and outcomes are in `tmp/dependency_development_v1`.
The calibration result therefore did not establish readiness.

The second corpus has 475 examples: 387 training and 88 calibration. It adds
240 examples with more short questions, draft followups and varied dependency
wording, plus 35 explicitly observed regression examples assigned to training.
The original cases and their extracted mixed fragments are therefore
**training regressions**, not held-out evidence. The frozen combined corpus is
[dependency_training_v2.json](dependency_training_v2.json), SHA-256
`ca0cab074d42a1d7bfc7036eec7c77e91d86e4da43516a63beef27a16b77e0a4`.

Six declared variants compare ridge regularization 0.1, 1 and 10 with BGE
feature weights 0.25 and 1; lexical weight remains 1. They share one CPU
embedding pass. Vocabulary, IDF and fitted weights use training rows only.
Calibration fits rejection thresholds and compares settings, so it is also
development data. Full artifacts are in `tmp/dependency_grid_v2`.

Variant 04 had the highest calibrated coverage but rejected the reported
headache followup and an ordinary draft edit. It was not promoted. A subsequent
explicit gate required all 20 labeled old cases and all eight original cases
to receive their accepted modes, and both mixed requests to retain their exact
general fragments. Variants 01 and 02 passed. Variant 02 had better calibration
coverage among those passing and was selected. The changed selection criterion
and all six outcomes are recorded in `tmp/dependency_candidates_v3`; no release
case was used for either selection.

The installed classifier uses regularization 0.1 and equal BGE/lexical weights.
Its calibration raw agreement is 82/88; 73/88 predictions are accepted with
zero observed accepted errors after threshold fitting. These fitted results
are not an error guarantee. In particular, the conservative `none` threshold
can cause unnecessary clarification on new wording.

Installed artifact SHA-256:
`7327983915ef766c1fb319a30fc0cce0c601ead01d2336be392c1a6ab1351983`.
Its canonical fingerprint is
`d10de3a977b4fd136050861a49a4b58fa8964cbca0cf683bb9947a3b10b22ad1`.
The artifact records the corpus, embedding identity, feature configuration,
class counts, source fingerprint and calibration settings. The offline-built
wheel was checked to contain the exact same JSON bytes.

The independently authored 32-case release set was frozen before these
candidate experiments, with SHA-256
`9d44076a5c1d7d3d248fdf53b99c740cd9367013f4b885f173c2acbd3a3da56b`.
The candidate was frozen before that set was opened. The release failed:
19/32 final dependency labels matched, although 29/32 raw labels matched.
Only 1/12 general requests received a general answer; ten unnecessarily
clarified and one incorrectly refused for missing personal memory. Neither
mixed request retained its general answer. Optional classification was 6/6,
but one optional plan failed before any model dispatch because its system
prompt exhausted the context budget. These are observed defects, not transport
failures. The independent review found zero unsupported personal facts, one
unsupported physical-action promise, and one explicit count failure.

The complete source snapshot is in `candidate_freeze_v1`, raw calls and
answers in `release_learned_v1`, the historical Boolean comparison in
`release_legacy_v1`, and separate routing/utility/evidence review in
`release_review_v1`. These 32 cases became development data after inspection.
The first release is not evidence that the repair was ready to deploy.

Subsequent development removes duplicated general-answer scaffolding to fit
ordinary optional plans within the existing 2048-token context budget, fixes
a generic offer-only detection gap, and checks bounded unsupported physical
action claims. It also investigates a single larger-model review of rejected
local predictions and proposed required dependencies. Review prompts and
schemas must be assessed on actual admitted production history; raw probe
outputs are retained, including unsuccessful variants and input mistakes.
The classifier weights and original fitted thresholds remain unchanged during
these review experiments. No new release success is claimed by these changes.

A second independently authored 32-case release set was frozen before the
next candidate, SHA-256
`abca3ad3fb364995b6673c6835b3bde28218c92e239266bc4b0825a02abe0eea`.
It remains separate from development until the next source freeze and replay.
