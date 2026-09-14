# Remaining independent sessions after a RAM-guard interruption

The first cascade session stopped during request 40 of 48 when the immediate
available-memory check crossed the frozen 768 MiB runtime floor. Its last
observation is interrupted; the eight later requests were not attempted.
The monitor latched the failure, models were unloaded, and final checks found
no cleanup errors, no resident models, unchanged boot/power/trip counters, and
no telemetry-reader error. This is a measured resource-feasibility failure
under the declared policy. It is retained in the primary comparison.

The 500 ms telemetry recorded peak whole-device RAM use of 6571 MiB, logical
swap use of 719 MiB, and temperature of 59.062°C. These sampled metrics do not
record the exact instantaneous `/proc/MemAvailable` value that triggered the
separate available-memory guard. The crossing magnitude cannot be recovered
from those samples. The failure does not establish a hardware crash or prove
that the application could never run with different resource policies.

An orchestration amendment continues the six untouched, independently planned
sessions in their original order: large round 2, cascade round 2, small round 2,
cascade round 3, small round 3, large round 3. Every new session starts from
request 1 with its own equivalent memory database. No answer in an existing
session is replaced and the missing tail of cascade round 1 is never filled.
There remain only three planned repetitions per arm; these are not extra
attempts selected for favorable quality or timing.

The frozen execution source, workload, inference settings, model identities,
and all startup/runtime limits remain unchanged. The existing below-54°C
scheduler handoff margin precedes the unchanged below-55°C child gate. A later
RAM-floor failure ends that session and remains recorded. Continuing to the
next independent session additionally requires verified clean unload, the
original boot/power/trip state, and a fresh pass of the original startup checks.
Other runtime failures stop this amended scheduler. A bounded cooldown cannot
override a failed startup gate. No swap, power, service, or user-application
settings are changed.

`scripts/continue_complete_system_schedule.py` is additional orchestration,
outside the frozen request source. Before launching session 4 it archives its
exact source and records its hash, dependency hash, original batch-finish hash,
all retained-session artifact hashes, and remaining slots in
`schedule_continuation_origin.json`. The existing `batch_finish.json` remains
untouched. New terminal sessions are journaled in
`continued_schedule_progress.jsonl`; the final amended schedule status is
written separately to `continued_schedule_finish.json`.

Analysis must distinguish schedule termination, attempted coverage, validated
delivery, and semantic correctness. A terminal schedule containing interrupted
sessions is not a completed 432-request collection. Observed correctness uses
attempted requests, with technical failures included; it is not full-workload
accuracy for an incomplete arm. Correct deliveries divided by all 144 planned
requests may additionally be shown as a conservative demonstrated-coverage
fraction, explicitly counting no unattempted request as a demonstrated success.
Both attempted and missing counts must accompany such results. Deadline curves
requiring complete collection remain withheld.

## Observed outcome of the amended schedule

Large-only round 2 completed all 48 attempts with 44 validated deliveries and
clean model unload. Logical swap rose from 718.5 MiB at its start to 833.75 MiB
at its finish, within the 1 GiB runtime ceiling but above the 768 MiB admission
ceiling for the next session. The following startup wait expired after its
900-second allowance without passing that unchanged admission gate. The
separate `continued_schedule_finish.json` records the final incomplete status.

No model or request was initialized for cascade round 2. Slots 5–9 remain
unattempted; this is a carry-over admission block, not a runtime failure of
those five systems/sessions. The primary population therefore contains 184
attempts, 166 validated deliveries, 17 output-check failures, one interrupted
attempt, and 248 unattempted requests. Three sessions completed their 48-item
workload, one stopped at 40, and five did not start. The original 12-request
diagnostic remains separate. No resource ceiling was relaxed and no swap
occupancy was forcibly cleared to complete the schedule.
