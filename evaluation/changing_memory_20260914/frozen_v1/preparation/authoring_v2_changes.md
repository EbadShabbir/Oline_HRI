# Prospective authoring revision v2

Revised before primary inference and before final runtime freeze.

`authored_v1` remains intact. The corresponding previous author generator and
protocol are also preserved in `authoring_source_v1`.

Version 2 sends the original first-person factual statement directly to the real
conversation, removing the artificial “Please acknowledge this personal
statement:” prefix. The statement's factual content is unchanged. This uses a
normal disclosure turn to exercise the production history path. All 288 questions,
mutation instructions, checkpoint times and expected-state ledger entries remain
unchanged; no observed answer motivated the change.

The protocol now accurately describes the production store as rebuilding the
eligible embedding matrix for repeated real lexical/semantic lookups, rather
than claiming a persistent vector cache. The retained original retrieval snapshot,
warmed BGE tokenizer/model and Ollama runtime state remain the actual stale/warm
state exercised by the experiment. No absent cache is introduced.
