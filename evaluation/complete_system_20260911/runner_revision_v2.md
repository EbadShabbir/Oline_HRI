# Runner revision 2: distinguish invalid answers from transport failures

Recorded after the first small-only session stopped at request 12, before
starting the replacement nine-session comparison. The original `freeze.json`,
protocol, workload, observations, and interrupted session remain preserved.
The previous launchers are archived under `runner_v1/`.

## Observed problem

The first session attempted 12 of 48 requests, delivering 10 validated answers.
Request `s2_t02` failed application validation. Request `s2_p12` raised
`OllamaError: Ollama assistant speech contains a reserved memory reference`.
The application correctly withheld that answer. The experimental runner
incorrectly categorized every `OllamaError` as a transport failure and stopped
the entire batch. No hardware boundary was crossed: peak RAM 5,642 MiB, logical
swap 483 MiB, temperature 57.906°C; no trip, reboot, or cleanup failure occurred.
No model remained resident afterward.

## Narrow correction

Two exact existing client errors describe invalid model-generated content:

- `Ollama assistant returned an internal memory ID`
- `Ollama assistant speech contains a reserved memory reference`

Revision 2 records these as failed requests and continues to the next request.
It does not accept, repair, or retry their answers. Other backend errors remain
fatal unless the deployed adaptive timeout fallback recovers within that turn.
The runner also records returned chat payloads before the client validates
them, preserving raw output and inference metadata for rejected answers.
Raw rejected output is never substituted for a delivered answer in scoring.
Production application code and every validation rule remain unchanged.

The workload, references, routing policy, models, generation parameters,
memory seed, counterbalancing, and resource limits are unchanged. The fix is
to failure accounting and observation capture; no answer-quality tuning was
performed. `freeze_v2.json` records the revised runner identity and links the
original freeze and this amendment.

## Analysis population

Restart all nine sessions in a fresh `complete-system-20260911-v2` directory.
The 432 planned replacement attempts form the primary comparison. Do not
merge or select among the original 12 attempts and the replacement answers.
Report the original 12 as a separate interrupted harness diagnostic, including
its two failed requests. The first 12 workload items therefore had preliminary
invocations before the primary run; retain that execution history when
describing this pilot. The original incomplete session is not a completed
small-only score.
