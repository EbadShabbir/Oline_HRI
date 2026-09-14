# Targeted repair hypotheses from baseline evidence

Prepared by an assistant after viewing sealed baseline diagnostics, before any
repair-validation inference. These are code-level diagnostic findings and
recommendations, not blinded answer judgments. Human validation is pending.

## Four evidence-selection omissions

The sealed answer analysis identifies `cm06_expiry_before_fresh`,
`cm07_correction_recalled`, `cm07_deletion_recalled` and
`cm07_expiry_before_fresh`: required current facts were present in storage and
retrieved, but no required evidence entered generation. The fixed uncertainty
delivery loses useful recall. The cm07 object is binoculars; cm06 is a sketchbook.

At baseline, `memory_evidence.parse_subject_request` recognizes direct locations
with `where (is|was) my ...`, excluding plural `are/were` (approximately line
323). Its `_facet_clause_supported` location predicate also omits `are/were`
(approximately line 442). `_request_head` conservatively rejects multiple
sentences except a small allowed output-instruction grammar, so the explicit
prior-memory preamble in unseen location questions yields no parsed subject
(approximately line 211). The fallback `direct_subject_supported` does not
recognize direct `where` questions.

`conversation._required_memory_ids` (approximately line 1543) requires at least
two descriptive overlaps or a stronger subject/relationship/temporal/preference
anchor. A single noun such as sketchbook or binoculars has one overlap and no
recognized anchor, causing exclusion despite retrieval. This agrees with the
observed empty supplied-ID list. Fix plural location grammar and recognize only
tightly bounded prior-memory preambles whose final explicit question names the
subject. Do not discard arbitrary first clauses or authorize a nearest neighbor
by one generic shared word. Include negative owner/attribute/multiple-question
tests so the broader grammar does not weaken subject linkage.

## Historical-control extra times

The 46 partial baseline historical-control answers supply the right venue and
also volunteer the event time, which the unchanged rubric forbids. Example:
`cm01_correction_historical_fresh` delivers the entire canonical picnic sentence.
Its answer constraint is null and its raw speech equals delivered speech: the
unrequested time is ordinary generation, not a postprocessing artifact. Required
evidence is correctly supplied. `conversation._memory_context` supplies the full
canonical fact, and current `grounded_composition.compose_verified_answer` has no
bounded single-location composer (approximately line 159).

A narrowly verified location answer can extract the requested positive location
from exactly linked evidence and exclude trailing time metadata when the query
asks only location. Match subject, owner and date first, reject negation,
conflicts, compound requests and unsupported syntax, and retain all context when
not confidently extractable. Expose any application-authored answer constraint
in traces and reports rather than crediting it as unconstrained model reasoning.

## Relationship and appointment validation

`conversation._collaborator_request_link` treats all adjectives before
partner/collaborator as required semantic qualifiers. This includes `current`
in the cm04 restart question even though that word is request framing. Exclude
only nonsemantic temporal/request modifiers; preserve meaningful qualifiers such
as walking or research so a different relationship cannot answer the question.

Temporal validation and composition consider correction-effective time alongside
canonical appointment content. A write/correction timestamp is provenance, not
the appointment start time. When the user asks the event start time, require the
canonical supported event clock and any requested date granularity; do not demand
the correction operation timestamp. Retain support for explicit questions about
when a correction took effect. Preserve raw and delivered answers separately:
five baseline withheld answers remain no-answer outcomes under their original
frozen judgments, whatever the repair changes later.

## Lifecycle policy

Baseline routing allows prior-turn references to set memory_required=false, and
generation history then contains old personal facts. Correct storage, purge and
snapshot checks do not protect this route. Current personal-memory questions
must reach live memory even when the question mentions earlier conversation.
History can supply conversational context but cannot authorize corrected,
deleted or expired facts. The changed runtime should be tested with retained
and fresh history and real process restarts, following the separate protocol.

## Reuse limitations

The production collection runner accepts a variable branch list. The original
schedule author, analysis v2, collection auditor and report-table renderer include
12/36/288-specific counts. The repair schedule author in this directory is a
documented copy with generalized counts. Analysis, audit and rendering must use
separately named copies adapted to the frozen 96-checkpoint workload, or a newly
validated generic implementation. Do not execute a baseline script that silently
labels a 96-row report as 288 rows. New answers require new blinded votes.
