# Development v2: retained failures and bounded repairs

Development v1 is complete and preserved separately: 16/16 final routes,
12/16 full-quality answers, 12/16 combined successes, no execution errors.
Both reviewers agree on all scored booleans. Cases 001, 004, 005 and 007 still
fail. This second iteration uses the same now-known sixteen-case corpus and
cannot supply new-case validation. The independent holdout remains unopened.

The v2 candidate permits matching consecutive model list markers to be stripped
before rendering the same application-owned numbering. Incorrect indexes and
empty marker-only items still fail. It adds checks/guidance for fixed supplied
plan durations, their associated actions/order and the requested total, within
the existing bounded retry flow. These checks do not prove arbitrary plan
feasibility or completeness.

For recognized arithmetic requests that demand only an integer, the model now
supplies a single bounded expression in `answer_parts`. The application accepts
only integer literals drawn from the current request, basic arithmetic and
parentheses, then computes an exact bounded integer using AST parsing and
rational arithmetic. Raw expression provenance remains recorded. No Python
evaluation, names, functions, powers or memory values are admitted. This
prevents unsupported operands and arithmetic execution errors within that
contract; it does not prove that the model selected the correct operations for
the request. Independent strict answer review remains necessary.

Public reference notes now include a bounded paper-fan construction note and a
clearer Earth-rotation note. Narrow contradiction checks and the existing answer
review/retry flow can reject some contradictory explanations. These are public
application notes, distinct from personal-memory evidence. Their presence is not
a correctness guarantee, as v1's incorrect day/night answer demonstrates.

Use the unchanged analyzer and protocol/review plan, but preregister the new
independent auditor and both of its standard-library helpers:

```text
../audit_results_v2.py
../independent_arithmetic_v2.py
../audit_reference_notes.py
../implementation_v2.md
```

The v2 auditor reconstructs exact arithmetic independently from source-bound
request values, verifies the raw-expression schema and limits, and verifies
consecutive numbering normalization. It checks public reference IDs against
literal constructors in hash-bound archived source, matching request topics and
the actual selected generation prompt; actual personal-memory fields must
remain empty. This replaces v1's mistaken assumption that all `reference_ids`
are personal-memory IDs. V1's original 260/261 audit and separate 5/5 reference
provenance supplement remain unchanged.

Run v2's audit with `audit_results_v2.py`, the v2 cohort directory and that
cohort's archived `candidate_source`. The analyzer invocation is unchanged apart
from cohort paths. New independent-auditor synthetic checks are recorded in
`harness_v2_offline_checks_v1.log` and its status JSON: 25 checks passed. V1's ten
preregistered artifact hashes were separately verified unchanged after this work.
