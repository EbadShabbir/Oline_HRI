# Offline check corrections

The first full discovery run used `PYTHONPATH=src:tests` and finished with 1,411 tests, 13 failures, one error, and 26 skips (exit 1). Its unmodified output is `full_offline_checks_v1.log`.

- The one error was an invocation error: a fresh subprocess could not import `scripts/independent_retrieval_supervisor.py`. The corrected invocation includes absolute paths for `src`, `tests`, and `scripts`.
- Seven subtest failures expected an immediate question with no missing-memory acknowledgment. The repaired behavior intentionally states that earlier information is unavailable before asking one question. Tests now require that acknowledgment, one question, unchanged provenance, no generated answer, no review or model calls, and withheld personal history.
- One general clarification test expected obsolete generic wording. It now checks one request for the task/result and retains the complete follow-up history and request checks.
- One mixed-request test expected a generic time/date question. It now requires the focused appointment-time question while retaining the isolated general fragment and evidence checks.
- Four wrong-route subtests expected the old generic fallback. They now require the missing-memory acknowledgment and one question, prohibit each fixture's unsupported answer, and preserve route metadata, retrieval count, no model calls, and empty history.

One substantive defect exposed by the last group was also fixed: when the user already names a person and asks about their relationship, the fallback asks for the relationship instead of asking for the already-supplied name. A focused test checks two supplied names, prohibits guessed relationships, and verifies that an actually missing identity still prompts for the name.

The first focused integration rerun failed two assertions because an edit matched the earlier of two identical assertions in a test file. That log is preserved as `clarification_integration_checks_v1.log`; the corrected 66-test run passed in `clarification_integration_checks_v2.log`. These corrections do not alter guard settings, model configuration, record validity, private-name handling, or the frozen original evaluation artifacts.

The corrected full offline run passed: 1,412 tests, 26 skipped, zero failures/errors, exit 0, 108.623 seconds. All five live-inference environment opt-ins were explicitly disabled. See `full_offline_checks_v2.log` and `full_offline_checks_v2.status.json`. The final `git diff --check` also passed.

Before development v2, the 197-test focused run exposed two runner fixtures
that expected a model review for an imperative explanation now handled by a
bounded task guard. Their prompts were changed to an equivalent general
question outside that grammar, preserving all raw-review, malformed-output,
call-count and clarification assertions. The original failing log remains
focused_checks_v2.log; focused_checks_v2_corrected.log passed all 197 tests.

The full v3 suite ran1439 tests with26 skipped and six fixture failures. All six
came from CLI tests expecting an imperative general task to call the reviewer
or retain classifier provenance after the new task guard resolved it. The
updated matrix explicitly covers guard, classifier and actual-review paths,
including uncertain raw input resolved by the guard, and preserves distinct
model roles, actual calls and full raw metadata assertions. The run's source and
tests remained unchanged while it executed. The subsequent117-test integration
run also covers the newly discovered LF search-boundary repair. Original logs
and statuses are retained; full v4 validation follows those corrections.

Full v4 passed: 1,440 tests, 26 skipped, zero failures/errors in 113.441 seconds.
The test launcher recorded unchanged runtime/test source throughout execution
and explicitly disabled all live opt-ins. Its exact log and status are frozen
with development v3, along with the 117-test final integration check.
