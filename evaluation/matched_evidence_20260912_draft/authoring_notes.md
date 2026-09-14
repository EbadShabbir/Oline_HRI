# Fresh matched-evidence dataset authoring

Status: assistant-authored draft, pending independent pre-inference review.
No generator inference or model-answer inspection was used in authoring.
The author first read `developments.MD`, `results.md`, and Stage 1 of
`evaluation/adaptive_selection_protocol_draft.md` to understand the existing
confounds and scope. No applicable ancestor `AGENTS.md` was found.

`build_dataset.py` deterministically writes `dataset.json`; it contains no
network or model calls. The dataset has 120 requests and 120 distinct scenario
IDs, with no dependent follow-up questions or shared fictional memory scenarios.
Every history is empty. Names, possessions, dates, quantities and wording were
newly authored here. Familiar general questions test ordinary household concepts;
they are not claims of novel facts or absence from pretraining. These cases do
not reuse prior fixture questions or prior model outputs.

| Category | Answerable | Unknown | Conflicting | Total |
| --- | ---: | ---: | ---: | ---: |
| Routine general | 24 | 3 | 3 | 30 |
| General with several explicit constraints | 24 | 3 | 3 | 30 |
| Direct personal recall | 18 | 6 | 6 | 30 |
| Personal temporal reasoning and synthesis | 18 | 6 | 6 | 30 |
| Total | 84 | 18 | 18 | 120 |

The general evidence cases describe fictional facilities/products, not personal
memories. All personal evidence is fictional and already supplied; no retrieval,
profile database, memory lifecycle or practical action is exercised. Unknown
cases omit a necessary answer field. Conflicting cases explicitly supply two
equally current/authoritative records with no correction or priority. Corrected
answerable cases explicitly establish which update replaces the old value.
Evidence order alone never authorizes resolution of an unresolved conflict.

References live only under each `rubric`; they must never enter the inference
payload. `required` lists semantic content and explicit task constraints;
`forbidden` lists particularly diagnostic wrong assertions. These are open
rubrics: paraphrases and other valid constructions are acceptable. References
are examples, not exact-string targets. A correct uncertainty response satisfies
an unknown/conflicting request where its rubric requires uncertainty. Mere
abstention on an answerable request does not receive full credit. Format/count
constraints apply to the answer text inside the shared response schema, not its
serialization punctuation. Numerical times may be expressed unambiguously in
12-hour or 24-hour form. Word limits count whitespace-separated words. Personal
answers should address the user consistently; no role-swapped robot memories.

Each question plus JSON-serialized evidence and empty history is below 1,200
UTF-8 bytes; the builder asserts this. This is only a dataset-size check. The
runner must separately verify the entire rendered prompt, schema instructions,
chat delimiters and generation reserve against the declared context before
collection. All example references are short enough for ordinary concise
responses within the 192-token output cap; references themselves are not model
inputs. The set is a balanced coverage workload, not a sample of household
frequency, independently collected human requests, or a routing benchmark.

Reproduction from this draft directory:

```bash
python3 evaluation/matched_evidence_20260912_draft/build_dataset.py
```

Do not rerun the builder over an immutable frozen experiment. Freeze reviewed
copies of the dataset and source only after independent review and correction.
