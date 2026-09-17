# Answer-quality repairs, 17 September 2026

Repairs cover invented personal recall, missing clarification, exact formats,
faithful shortening, arithmetic and supplied-time preservation. The newest
test suite reports **1,489 passes and 26 live-only skips (1,515 total)**. Its final live
validation is pending; this is not a release-quality pass.

| Cohort | Planned / recorded | Final routing | Full quality | Device outcome |
| --- | ---: | ---: | ---: | --- |
| Previous recovery baseline | 16 / 16 | 12/16 | 4/16 | Clean |
| [Development v1](development_v1/README.md) | 16 / 16 | 16/16 | 12/16 | Clean |
| [Development v2](development_v2/README.md) | 16 / 12 | 11/16 | 9/16 | RAM guard; one error, four unattempted |
| Development v3, newest source | 16 / 0 | Unmeasured | Unmeasured | Administrator prompt timed out before collection |
| Independently authored twenty cases | 20 / 0 | Unmeasured | Unmeasured | Unopened pending final freeze |

These sixteen development prompts were previously observed. Both independent
reviewers agreed on all scored Booleans in each recorded cohort. V1 gained eight
full passes and retained the four baseline passes. Its remaining failures were
the supplied-time plan, paper-folding instructions, arithmetic and daily-cycle
explanation. V2 corrected the paper-folding and arithmetic answers, but its plan
validator falsely rejected a correct total wording and its daily-cycle answer
remained incomplete. The newest source repairs both issues; it still needs its
complete live replay and unseen evaluation.

V1 complete-turn median/p95 was **3.804/14.394 seconds**; zero execution errors,
clean model unloading, maximum sampled swap 685 MiB and temperature 57.406°C.
V2 observed-turn median/p95 was **5.403/20.754 seconds** across twelve recorded
cases. Missing observations retain no invented latency. These historical
sessions are descriptive, not a causal speed comparison.

V1's original audit remains **260/261**, retaining its mistaken treatment of a
static public-reference identifier as personal-memory evidence. The separate
reference provenance supplement passes **5/5**, and the incorrect answer stays
failed. The corrected independent V2 auditor verifies arithmetic and public
references; its **260/263** result retains the RAM failure and incomplete
observation/review coverage.

The [cleanup audit](device_cleanup_v1/README.md) passes **38/38** restoration
checks. Existing swap size, priorities and configuration were preserved. RAM
still fell short of the 2 GiB startup gate. [Read-only headroom evidence](headroom_audit_v1.json)
identifies an idle firmware updater that can be temporarily paused and restored.
The normal administrator prompt timed out; [the attempt log](development_v3/updater_pause.jsonl)
records that no evaluation started. Active IDE, remote and robot processes were
not stopped, and device guard limits were not relaxed.

The [final status check](updater_pause_v1_final_status.json) confirms that the
updater remained active and idle and that no administrator-prompt process was
left running. The separate [revised pause helper](run_with_idle_updater_paused_v2.py)
has [twelve passing offline lifecycle checks](updater_pause_v2_offline_checks.log).
It avoids asking to restart a service that never stopped and preserves recovery
when evaluation cleanup fails. This helper has not been exercised with a real
administrator operation; the original failed attempt and sealed helper remain
unchanged.

Implementation records: [initial repairs](implementation.md),
[second candidate](implementation_v2.md), [newest candidate](implementation_v3.md).
Validation: [full-suite log](full_offline_checks_v4.log),
[exact source/test hashes](full_offline_checks_v4.status.json).
The failed first offline invocation is retained: a missing subprocess import
path was corrected in the launcher before the successful suites.

The [protocol](protocol.md), [review plan](review_plan.md) and [commands](commands.md)
retain the separation of known replay and unseen cases. Use `audit_results_v2.py`
with `independent_arithmetic_v2.py` and `audit_reference_notes.py` for later
cohorts; original sealed audit files remain immutable. No final holdout source
freeze, case opening or model dispatch has occurred.

Exact prior README/results bytes are preserved in
[baseline_snapshot/manifest.json](baseline_snapshot/manifest.json), keeping
older seals verifiable after these index updates. All earlier evaluation
folders, raw outputs and reviews remain unchanged. Voice/transcription,
end-to-end audio latency and live populated-memory behavior still need separate
validation on the eventual candidate.

GitHub publication remains pending: the earlier mixed source/test/evaluation
commit was rejected before push execution by automatic approval review, which
requires explicit approval for that full payload. No successful push is claimed.
