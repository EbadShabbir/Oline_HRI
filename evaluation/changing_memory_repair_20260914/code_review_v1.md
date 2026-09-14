# Assistant code review — changing-memory repair

Independent review of the parent-authored conversation and location-composition changes, with adversarial review of the evidence and correction-time helpers. All five independently identified findings were resolved before this receipt. The reviewer authored the routing change; its self-review is explicitly separate. This is code review, not a blinded delivered-answer review or a live-model score. Human code validation remains pending.

Validation: **96 focused tests passed**, plus **28 independent adversarial and positive-boundary assertions**. Source hashes were stable during the focused test run. The exact command, sources and log hashes are in [code_review_v1.json](code_review_v1.json); output is in [code_review_tests_v1.log](code_review_tests_v1.log).

| Finding | Resolution |
|---|---|
| Location composition removed a dated historical qualifier for a current-location question. | Question and source tense must agree; a date is omitted only when the question explicitly supplies the event date. |
| The new location early return bypassed canonical/event_time date consistency checks. | Location composition now follows the existing canonical and metadata date coherence check. |
| Conditional locations entered the verified-location shortcut despite the bounded composition contract. | Conditional suffixes including unless and except now decline extractive composition. |
| Temporal-only on Monday, at noon, in June and ISO-date values could be treated as locations. | The shared evidence slot rejects wholly temporal values while preserving named venues such as Monday Hall, June Room and Room 12. |
| Event-time questions mentioning a prior change could request correction metadata even without asking when the change occurred. | Correction-time detection now requires a question predicate targeting change, an explicit time-of-correction request, or an explicit chronology about when the change happened. Four adversarial event-time counterexamples now remain false. |
| Self-review of the new routing followup heuristic found generic assistant phrases containing your or you have could trigger personal routing. | The heuristic now requires an initial personal fact assertion and excludes generic question/example/code subjects. Three general-topic counterexamples pass. |

Memory requests omit old factual history from generation while preserving the bounded session for routing. Snapshot validation remains before generation and delivery. General followups retain context, and concrete personal examples were removed from generation instructions.

The repair does not establish universal non-disclosure: unsupported paraphrases still depend on classification, and unresolved pronouns may abstain. Declining an extractive composition does not itself repair inconsistent source data. Offline checks do not establish live model quality, power-loss recovery, or spoken performance.
