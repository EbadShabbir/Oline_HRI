# Supplementary reporting scope

This snapshot supplements the frozen core analyzer. It does not replace its disjoint timing audit or its dependent-sequence analysis. During collection, an active session without finish.json is explicitly omitted; terminal batches include unfinished attempt directories.

The core turn output-token field uses delivered generation metadata and is missing for rejected answers. These tables instead retain backend_response token counts from every actual backend_chat span, including generation later rejected by validation. Calls, client HTTP records and trace metadata describe the same operation and are not summed as separate calls. Unknown metadata remains missing.

Backend load/prefill/decode durations overlap the measured wall spans. All-backend loading includes classifiers and generators; a cold classifier can pay the load which the diagnostic replay pays in generation. Generation-only load differences must not be presented as net loading savings. No backend duration is added to sequence or request totals.

The primary sequence total is startup plus requests plus measured gaps. Cleanup is shown separately. Paired component deltas use adaptive minus comparator; positive values mean adaptive is slower or uses more tokens. Exact replay inputs do not ensure identical placement, output length, numerical execution, cache state or temperature. The replay also has a fixed last position. Direct residency-audit subtraction is a diagnostic and does not remove these confounds.

DDEE route tables show selected and actual LLLS separately. A small-model return on turn4 has no observed following request. Report that absence explicitly; do not infer a fifth-turn saving from EEEE resident requests. Following-turn rows preserve their actual preceding transition, workload position and model. GPU allocation fractions are allocated bytes, not utilization or compute fractions.

Per-pattern/per-repetition tables are descriptive. Three repetitions of a sequence are dependent, and shared templates/profile further limit independence. Review is optional input here; no useful-answer or quality–latency improvement follows from faster execution or validated delivery alone. The original interrupted validation-failure turn remains a failed answer after the exact audited sequence-eligibility repair.
