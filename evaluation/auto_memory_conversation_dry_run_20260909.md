# Automatic-memory conversation dry run — 9 September 2026

Storage worked in this run, but broader question answering was only partially
successful. All seven intended facts were saved exactly and survived a process
restart. Three of seven distinct stored facts were answered correctly after
restart; two unknown-answer controls correctly produced an abstention.

## Setup and scoring

- Real local Ollama `qwen3:0.6b`, configured temperature `0.2`, with the production
  router, generator, BGE/SQLite retrieval, automatic capture, and interactive
  `_run_chat` loop. This was scripted text input, not a microphone/STT/TTS test.
- Ten natural opening lines: seven distinct facts, a greeting, a temporary
  feeling, and an exact repeated preference. No `/remember` commands or direct
  memory inserts were used.
- Three same-session questions, then nine questions in a separate Python
  process: seven known-answer questions and two unknown-answer controls.
- The test used an isolated database and fictional information. The normal
  personal-memory database was not used. Application-source hashes matched
  across both phases; no application fixes or answer retries were made during
  the run.
- Expected capture outcomes and answer content were defined before execution
  in the [runner](../scripts/run_auto_memory_dry_run.py). Answer scoring below
  is semantic review of the visible answer, required details, and memory IDs,
  independently cross-checked against the raw records. A valid JSON response
  alone does not count as a correct answer.

| Check | Observed result |
| --- | --- |
| Store/skip/duplicate decisions | 10/10 as expected |
| Exact unique statements stored | 7/7 |
| Correct memory category | 6/7 |
| Same-session known-answer questions | 3/3 correct |
| Known-answer questions after restart | 3/7 correct |
| Unknown-answer controls after restart | 2/2 appropriate abstentions |
| All known-answer attempts, including repeated topics | 6/10 correct |
| CLI error returns | 2 of 22 conversational turns |
| Records before versus after restarted Q&A | 7, unchanged |
| Expiry timestamps | 7/7 exactly seven days after creation |

The same three topics were tested successfully both before and after restart.
These are small-sample observations, not an estimate of general accuracy.

## The ten-line conversation

The following replies are the actual application-visible outputs.

| # | Human input | Robot reply | Capture result |
| --- | --- | --- | --- |
| 1 | Hello, let's have a chat. | Hello! How can I help you today? | Skipped |
| 2 | I prefer peppermint tea without sugar. | You prefer peppermint tea without sugar. | Preference saved |
| 3 | My robotics meetings are Thursday afternoons. | Your robotics meetings are on Thursday afternoons. | Routine saved |
| 4 | Maya is my sensor calibration partner. | Maya is your sensor calibration partner. | Relationship saved |
| 5 | I own a green bicycle. | Thanks for telling me. | Fact saved |
| 6 | My desk plant is named Sprout. | Your desk plant is named Sprout. | Saved as **event**; expected **fact** |
| 7 | I completed a camera calibration test. | I completed a camera calibration test. | Event saved; reply uses the wrong speaker |
| 8 | I prefer short answers. | Thanks for telling me. | Preference saved |
| 9 | I feel tired right now. | I feel tired right now. | Skipped correctly; reply uses the wrong speaker |
| 10 | I prefer peppermint tea without sugar. | Thanks for telling me. | Duplicate: existing ID and deadline retained |

Eight of ten initial replies were acceptable acknowledgments. The event and
mood replies mirrored the human's first person. Three other first-person model
echoes were replaced with the application's neutral acknowledgment before
display. The existing guard helps but does not cover all forms of self-reference.

The subsequent same-session tea, meeting, and partner questions each returned
the correct complete answer with its relevant memory ID.

## Questions after a process restart

| Question | Actual visible outcome | Assessment |
| --- | --- | --- |
| What kind of tea do I prefer? | You prefer peppermint tea without sugar. | Correct |
| When are my robotics meetings? | Your robotics meetings are on Thursday afternoons. | Correct |
| Who is Maya to me? | Maya is your sensor calibration partner. | Correct |
| What color is my bicycle? | I do not have a verified personal memory that answers that. | Incorrect abstention: green bicycle was stored |
| What is my desk plant's name? | `chat error: request could not be completed safely` | Failed: expected Sprout |
| What test did I complete? | I completed a test related to your knowledge base. | Incorrect, unsupported answer; expected camera calibration test |
| Do I prefer short or long answers? | `chat error: request could not be completed safely` | Failed: expected short answers |
| What is my dog's name? | I do not have a verified personal memory that answers that. | Correct abstention |
| When is my birthday? | I do not have a verified personal memory that answers that. | Correct abstention |

Evidence explains the four known-answer failures:

1. **Bicycle:** the correct record was retrieved and supplied. The model generated
   “Your bicycle is green.” but omitted its required memory citation. The
   application replaced the answer with an abstention. This was not lost storage.
2. **Plant:** the model generated the correct name, but cited the plant, partner,
   and meeting records together. Validation rejected citations not linked to the
   question. The category error is a separate observed problem; this run does
   not establish it as the cause of the answer failure.
3. **Completed test:** the router classified the question as a statement with
   `memory_required=false`. Retrieval never ran, and an unsupported answer reached
   the user.
4. **Answer length:** the model mixed the short-answer preference with tea and
   calibration facts, citing unrelated records. Validation rejected it.

For the birthday control, the raw model invented “April 15th.” The application
blocked that answer and displayed the correct abstention. The successful control
therefore reflects the combined application and model, not reliable raw-model
factuality.

## Observed timing

“Response ready” measures from submitting a line to a response or error becoming
available. “Full turn” additionally includes automatic capture after the reply.
The instrumentation adds small bookkeeping overhead; these are not calibrated
hardware benchmarks. Error returns are included in the Q&A timing figures.

| Stage | Turns | Mean response-ready time | Mean full-turn time |
| --- | ---: | ---: | ---: |
| Opening conversation | 10 | 1.55 s | 2.16 s |
| Same-session Q&A | 3 | 2.23 s | 2.23 s |
| First Q&A after restart | 1 | 17.41 s | 17.41 s |
| Remaining Q&A after restart | 8 | 2.17 s | 2.17 s |

- Warm restarted Q&A ranged from **1.71 to 2.89 seconds**, including two errors.
- The first restarted reply included **12.03 seconds of Ollama model loading**.
  BGE was also initialized again in the new process. The opening conversation
  used an already-loaded Ollama model, as indicated by its reported load times.
- New-memory capture after the first initialization added **0.42–0.50 seconds**
  after the reply. The first capture, including embedding initialization, took
  **2.98 seconds**. Checking the repeated statement took about **0.006 seconds**.

## Persistence and follow-up priorities

The process IDs differed (`975380` and `975464`). All memory records, including
IDs, exact text, categories, and deadlines, were identical at the end of learning,
start of restarted recall, and end of recall. Questions added no memories. The
seven-day deadlines were verified mathematically; actual expiration cleanup
after a week was not exercised in this short run.

The next improvement should focus on general recall and citation selection,
especially possession attributes, names, and preference comparisons. Event
questions also need more reliable routing. Broader first-person acknowledgment
handling and more accurate memory categories remain useful follow-up work.

## Saved artifacts and reproduction

- [Learning phase: full inputs, outputs, timings, model calls, and database snapshots](../tmp/auto_memory_dry_run_20260909_01/learn.json)
- [Restarted recall: full inputs, outputs, timings, model calls, and database snapshots](../tmp/auto_memory_dry_run_20260909_01/recall.json)
- [Learning terminal output](../tmp/auto_memory_dry_run_20260909_01/learn_stdout.txt) and [diagnostics](../tmp/auto_memory_dry_run_20260909_01/learn_stderr.txt)
- [Recall terminal output](../tmp/auto_memory_dry_run_20260909_01/recall_stdout.txt) and [diagnostics](../tmp/auto_memory_dry_run_20260909_01/recall_stderr.txt)
- [Isolated configuration](../tmp/auto_memory_dry_run_20260909_01/config.json); database alongside it at `memory.sqlite3`.

From the project root, reproduce using a new, unused run directory:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_auto_memory_dry_run.py --run-directory tmp/auto_memory_dry_run_next --phase learn
PYTHONPATH=src .venv/bin/python scripts/run_auto_memory_dry_run.py --run-directory tmp/auto_memory_dry_run_next --phase recall
```

To continue chatting with this run's fictional records:

```bash
PYTHONPATH=src .venv/bin/python -m oline_hri --config tmp/auto_memory_dry_run_20260909_01/config.json chat --auto-memory --show-route --show-memory-ids
```
