# Response-quality temperature A/B v2 gate amendment

Recorded before the next complete gate rerun on 2026-09-08. The original
protocol remains unchanged.

The first two completed gate runs failed closed because the model named its
machine-only memory aliases in speech. After the boundary and prompt fixes, an
offline replay showed that an otherwise correct, alias-free answer was rejected
only for omitting `09:00` and `10:00`. Those clocks come from semantic metadata;
the frozen prompt, reference answer, required claims, and gate criteria ask for
the two dates and their ordering, not clock precision.

Before another live sample, temporal completeness was therefore scoped as
follows:

- Metadata-only `clock:*` claims may be omitted only for an explicit chronology
  request that does not request clock precision.
- At least two cited chronology-bearing records must each resolve to exactly one
  valid full date, and those dates must be pairwise distinct.
- Missing, invalid, conflicting, ambiguous, or same-day dates disable the
  exemption.
- Clocks stated in `canonical_text` remain mandatory. Explicit time questions
  still require metadata clocks, and generated unsupported clocks still fail.
- Weekdays, dates, month/day values, dayparts, citations, fact coverage, and
  anti-invention validation remain unchanged.

This aligns application validation with the preregistered case contract without
changing stored data, the rubric, candidate settings, or any observed model
answer. Focused regressions and an offline replay must pass before the new live
gate directory is created.
