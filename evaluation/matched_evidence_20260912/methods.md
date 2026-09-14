# Frozen experimental method and artifact guide

This experiment measures the two installed generators on matched supplied evidence.
It bypasses CLARA's routing, retrieval, memory selection, answer composers, literal
answer constraints, rewriting, validation replacements, and cross-model fallbacks.
No personal database, embeddings, speech pipeline, or actuator path is called.
The same evidence-controlled result must not be described as retrieval accuracy,
end-to-end CLARA quality, or a measured benefit of an adaptive selector.

The dataset contains 120 fresh assistant-authored questions, one independent fictional
scenario each, with 30 cases in each of four categories. A separate assistant reviewed
every question, evidence set, rubric and illustrative reference before inference and
approved the exact dataset hash after seven clarifications. There are 84 answerable,
18 unknown and 18 conflicting cases. Routine and constrained general categories each
have 24/3/3; each personal category has 18/6/6. Familiar general knowledge is not claimed
to be absent from pretraining. No exact normalized match was found among 3,149 prior
question fields; this is a local freshness check, not semantic novelty certification.

Both generators receive the same explicit Qwen3 raw chat prompt, including every
provided evidence record and empty history. Reference answers, rubrics, category labels,
evidence-status labels and IDs stay outside the request. The common response schema
allows an arbitrary answer string; it does not enumerate or supply a solution.
Context is 2,048 tokens, output cap 192, temperature 0, seed 42, thinking disabled.
Identical GPT-2 byte-BPE metadata and all 256 ordinary byte symbols were verified in
the installed GGUF files without loading weights. The largest conservative prompt
bound plus 192 output tokens and 64 reserve tokens is 1,020/2,048. The raw endpoint
avoids server chat-template differences; the installed templates also match.

The twelve model blocks implement six paired twenty-request blocks, five cases per
category in each. Model order is AB/BA/AB/BA/AB/BA, with A=0.6B and B=1.7B. Every paired
block uses identical question order. Models are explicitly preloaded alone, retained
for twenty requests, then unloaded. Inference is serialized; before/after residency
checks verify model name, frozen digest and 2,048-token context. Automatic CPU/GPU
placement is observed, not forced. Prompt-prefix caching may occur within each block;
it is part of this common resident-workload condition.

The existing device policy reserves 256 MiB of the already configured logical swap
capacity, with unchanged physical-memory and thermal guards, active fan checks,
15W power mode, boot/trip checks and 500 ms tegrastats. No swap device, service, power
setting, cooling setting or other OS configuration is changed. The collector uses a
cooperative process lock; before/after observations do not prove that no unrelated
client could act between checks. Explicit startup waits are logged outside measured
warm request time. The absolute request deadline is 120 seconds, and telemetry-stall
or resource violations interrupt collection. No primary attempt is retried.

Raw HTTP bytes are persisted as base64 chunks before parsing. Durable starts preserve
attempt accounting on interruption. Invalid JSON, truncations, errors and timeouts
remain in the denominator; no application rewrites the answer. Total HTTP latency
includes streamed-byte logging overhead, common to both arms. Preloads, backend
loading residuals, prefill and decoding are reported separately; summing overlapping
backend and wall metrics would double-count. Complete-request wall time is neither
time to first token nor time to speech. Telemetry is whole-device VDD_IN with no idle
subtraction; sampled RAM, shared CPU/GPU allocations, and logical zram occupancy must
not be added into a fictitious memory capacity.

Two independent assistants review randomized opaque answer IDs in fresh contexts,
using only question, complete evidence, rubric, answer and response-completion status.
They receive no model/timing/order/mapping information and do not see each other's
judgments. Both files are frozen before comparison; a third blinded assistant resolves
all label/flag disagreements before unblinding. Blinding is procedural in a shared
filesystem, not an enforced operating-system access partition. Independent human
validation of questions and answers remains pending.

Success means the full rubric is satisfied, including appropriate abstention or
uncertainty where required. Partial answers get their own label but no full credit;
unsupported guesses, inappropriate abstentions and technical failures do not succeed.
Paired outcome counts include small-only wins and neither-correct cases. The descriptive
95% quality-difference interval resamples whole scenarios within each equal-size category
10,000 times with seed 42121. Shared authorship and reasoning patterns limit generalization;
this is not a random sample of household request frequencies or a powered user study.
No quality floor, acceptable extra-cost threshold, deadline or equivalence margin is
chosen after results. The experiment can demonstrate observed useful rescues and their
measured cost; it cannot establish that a deployable router identifies those cases.

Artifact directories are exclusively created and sealed with SHA256 manifests and
read-only permissions. This is local application-level immutability, not privileged
write-once storage. The final experiment manifest covers all retained artifacts.
Previous experiments and working application source are preserved.
