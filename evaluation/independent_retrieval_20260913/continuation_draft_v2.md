# Second explicit continuation: unchanged execution and guard limits

The procedural rules in the sealed
[first continuation amendment](continuation_v1/protocol_amendment.md) remain
in force. This new plan changes only the immutable prior-prefix record and
the one authorized output directory. The original 44 execution files and
four supplemental continuation files remain byte-identical. The frozen test,
models, memory snapshot, decoding, prompts, helpers, validators, rubrics,
analysis rules, resource limits and device baseline remain unchanged.

The sealed cumulative `run_v2` now contains 184 attempts: 182 delivered
observations and two interruptions by the unchanged available-memory runtime
floor. The additional physical fragment executed 27 previously unattempted
requests in logical block 4. Its final attempt, original scheduled position
40 (`ir_03_02`), remains an attempted failure. Neither interrupted request nor
any delivered request may be retried or replaced.

An independent metadata audit must verify the exact unique 184-request prefix,
the previous continuation and ledger seals, source hashes, cleanup, snapshot,
device baseline and durable start/observation correspondence. The next suffix
is block 4 positions 41–48 (eight requests), followed by blocks 5–18 (672):
exactly 680 unattempted requests. Freeze this plan as `continuation_v2`,
authorized only for the new `run_v3` directory.

The unchanged supervisor still seals a separate one-use ledger per physical
admission, retries only proven zero-request resource admission rejections
within the existing bounded window, and stops at any further fatal request.
There is no planned chunking or automatic retry of an attempted request.
Further continuation requires another explicit independently reviewed plan.

Report both interruptions, their request times, additional loading costs and
the additional physical boundaries. There remain 18 planned logical blocks;
completing all requests will now require at least 20 physical fragments.
Repeated memory-floor interruptions limit claims about sustained large-model
residency. They are observed experimental failures, not grounds for changing
the frozen workload or resource limits. The pause and boundary-gap accounting
from the first amendment continues to apply. Human validation remains pending.
