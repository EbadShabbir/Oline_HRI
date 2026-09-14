# Resume independent sessions after a startup-only temperature rejection

The revised runner completed small-only round 1: 48 attempts, 42 validated
deliveries and six withheld answers. This complete session remains unchanged.
When handing off to large-only round 1, the scheduler observed a temperature
below 55°C, but the child process's independent check measured 55.218°C.
It rejected startup before initializing embeddings, loading a model, or
attempting any request. The two readings illustrate a small thermal fluctuation;
no runtime guard was crossed and no answer was retried.

The remaining eight sessions resume in a new `complete-system-20260911-v2-resumed`
directory. Its first slot links to the already completed 48-request session,
whose observation and finish hashes are recorded in `resume_origin.json`.
All subsequent slots run in fresh directories. The prior batch, original
startup-rejection files, and complete first session are preserved. No partial
request session is combined with a continuation or substituted output.

The resume scheduler waits for below 54°C before launching a child, giving
margin for temperature fluctuation. The frozen per-arm admission gate remains
below 55°C; device limits, request order, models, generation settings, memory,
and application source are unchanged. Additional startup-only temperature
rejections, if any, are retained under `startup_rejections/` and may be retried
only when no model/request initialization occurred. Other failures stop the
batch. Waiting time is outside request latency and remains part of the
recorded experiment chronology.

`resume_complete_system_batch.py` is additional orchestration code, recorded
by SHA-256 in the resume origin record. Every actual request still executes
the runner and source files pinned by `freeze_v2.json`. Analysis includes the
completed first session once and the eight resumed sessions once, retaining
the original counterbalanced nine-session order.
