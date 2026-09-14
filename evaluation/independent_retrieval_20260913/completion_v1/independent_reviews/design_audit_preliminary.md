# Independent pre-inference design audit

Reviewer: independent assistant agent `/root/audit_design`, 2026-09-13.
This agent did not author the dataset or adapter and did not run inference.
Human validation is pending. This preliminary record is not collection approval.

The reviewer read the user specification, `developments.MD`, `results.md`,
`evaluation/adaptive_selection_protocol_draft.md`,
`evaluation/memory_pipeline_20260912/README.md`, and
`evaluation/post_memory_comparison_20260912/README.md`, and inspected the
production memory intent, conversation, fixed-system, retrieval and memory
implementations.

The six-arm controlled ablation is appropriate if the following are satisfied:

1. Authorization is independent from relevance. OFF performs no retrieval;
   ALWAYS attempts every authorized request; SELECTIVE alone pays for any
   necessary model classifier on its condition's sole generator.
2. Common deterministic response intent does not use ground truth, reference
   labels, or SELECTIVE model classifier output. Common helper behavior changes
   only with request-linked evidence, with those changes recorded. In particular,
   unrelated ALWAYS candidates must not disable a general-answer helper.
3. With empty supplied evidence, generation prompts and schemas must match
   across policies for a given request. OFF must have empty fresh history and no
   path by which snapshot facts enter model requests, helpers or validators as
   answer references. Lifecycle authority remains active when evidence is used.
4. Exact cosine search reads every eligible profile record, before returning
   at most twenty semantic candidates. Record corpus inspection separately
   from semantic/keyword candidates, returned retrieval results and evidence
   supplied to the generator. Counting only three retrieved records as all
   inspected records is insufficient.
5. Relevance labels express whether the task warrants search, rather than
   whether the snapshot contains an answer. Unknown and lifecycle questions may
   warrant search with no answerable evidence. Declare unnecessary-access
   denominators before inference.
6. Use whole request/scenario units for paired uncertainty, retaining all three
   timing repetitions and any differing quality outcomes within those units.
   Three repeats do not create 144 independent quality cases per condition.
   Equal observed rates alone do not establish noninferiority.
7. The user-requested success rubric applies to OFF unchanged: cautious
   abstention on a known authorized fact is failed personalization. Record
   caution separately. Conflicts must retain both contradicting records in
   relevant evidence, with uncertainty required by the answer rubric.
8. Freeze exact questions, snapshot inputs and lifecycle operations, references,
   rubric, protocol, source/configuration and model digests after independent
   review and before measured inference. Hash the actual prepared database and
   verify fixed snapshot state before and after each session.
9. Hold model tag fixed in all classifier, helper rendering, generation and
   fallback paths; retain sole-model residency within sessions and preserve
   guards, serialized device execution, raw failures and interrupted sessions.
10. Blinded reviewers should receive only question, common rubric and answer
    under randomized IDs, with model, condition, timing, mapping and reference
    provenance that encodes condition withheld until judgments are frozen.

The response-intent adapter is an experimental control rather than proof that
the unchanged production pipeline isolates memory access. The final report
must say so, and report evidence-dependent helper effects as application
behavior rather than ordinary generator reasoning.
