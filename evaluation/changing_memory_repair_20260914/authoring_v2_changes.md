# Repair validation authoring provenance

This separately labeled diagnostic rerun reuses baseline scenarios cm01, cm04, cm07 and cm09 without changing their questions, facts, event schedule, expected states or answer rubrics. The name of this file satisfies the existing freeze interface; no claim of a second repair-authoring revision is made.

The independent schedule author was copied from the sealed baseline and generalized only its experiment label and workload-count assertions/manifest field. It still imports no CLARA runtime modules and reads no delivered answers or live database state. The four scenarios were selected after inspecting baseline failures to cover preference hallucination/stale history, relationship validation, plural-object evidence omission and appointment-time validation. Historical-control events remain in each scenario. Mutable dated-event subject scenarios cm11/cm12 are not part of this targeted subset.

This is a development regression check, not held-out accuracy estimation or a replacement for the original 288 checkpoints. Original unfavorable traces and frozen judgments remain unchanged. New answers require new independent blinded assistant reviews before diagnostic unblinding; human validation remains pending.
