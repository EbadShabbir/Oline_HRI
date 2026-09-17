# Changes under validation

The learned dependency classifier and its training artifact are unchanged.
Uncertain, clarification, unverified-required and unresolved-edit decisions can
receive one four-mode review. Explicit absent personal recall remains required;
the review cannot turn that into authority to invent a personal answer. Raw
classifier predictions and the separate final dependency remain visible.

Sizing is now an application policy with versioned provenance. Substantive
general tasks use the configured large generator; short social turns may use
the small model. A clarification needs no generation, and required recall first
goes through retrieval. No model is loaded merely to predict model size. The
existing client already retained repeated same-model calls correctly, so it was
not changed. Generation and answer review can now use the same resident model.
Actual model calls remain recorded; omitted compute calls have null generation
metadata. No new simultaneous residency or device limits are introduced.

General answer instructions permit requested line breaks and stop imposing a
software-validation-plan template on every household plan. LF is accepted in
current text and delivered speech; other unsafe output controls remain blocked.
Internal-memory-ID checks also reject identifiers split across LF. The reply
still has the exact JSON contract, authorized memory selectors and NO_ACTION.

Conservative task checks cover explicit global sentence/line/bullet/equation
counts, requested CSV structure and explicit minute-allocation sums. They check
the generated component of a mixed answer, without pretending to prove meaning
or feasibility. Ranges, approximate limits, quoted/source counts and per-item
counts are excluded from the exact-count grammar. CSV discussion is distinct
from a CSV output directive. Failures supply closed application-owned feedback;
rejected prose does not become task context. A task already using a large model
can receive one repair on that same model, still within two generation attempts.

Missing-recall replies acknowledge unavailable information and ask for a subject
drawn from the actual question. Ambiguity replies ask for the missing operation
or referent. Bounded supplied event-announcement/invitation drafts can remain
editing context, including an ordinal follow-up; that requires actual admitted
artifact context. Personal disclosures and ungrounded prior assistant claims
remain outside reusable history. Ordinary evidence checks and final disclosure
freshness apply independently of routing and format checks.

The new format and history grammars are intentionally bounded. Model review is
fallible; neither these checks nor the deterministic size policy establish full
answer correctness. Live development and fresh validation results are recorded
separately before any improvement claim is made.

Development v1 exposed an integration defect: the general task instructions
were present in a historical routed Conversation path but absent from the
un-routed Conversation used by ReliableConversation. V2 attaches them to the
actual general generator system message; an integration test inspects the
request received by the backend. The output schema no longer says prose-only.
Qualified counts (for example a polite two-sentence invitation) are recognized,
and missing-recall replies distinguish explicitly mentioned assistant guesses
from actual user statements without echoing their guessed values.

V3 uses closed answer_parts arrays for recognized exact line/bullet/item/sentence
formats and CSV rows. The app renders separators and markers without rewriting
model words. Closed steps_for_user output can also serve explicit timed plans:
positive integer shares sum to the supplied budget, with an explicit bounded
phase count when requested. Original JSON, actual call roles and response
transforms remain recorded; the same evidence/format/review gates apply.
The app does not establish that actions are feasible or semantically complete.
Explicit counted-word constraints are checked across rendered text. Memory IDs
are rejected across internal line splits and at normal line boundaries.

The v2 audit found that current LF requests were still rejected by search.
HybridRetriever now converts only LF to spaces before both backend searches.
Original conversation text and stored records are unchanged; existing backend
validation continues rejecting all other controls. An integration test uses a
real isolated MemoryStore, validates retrieval/currentness, rejects other
controls, then deletes the record and confirms it is no longer retrievable.
