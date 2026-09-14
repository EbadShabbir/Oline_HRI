# Independent analysis audit before collection

Reviewer: independent assistant `/root/audit_design`. No primary outputs seen.
Reviewed `scripts/analyze_independent_retrieval.py` and its six initial offline
tests. This is a code/design audit, not a semantic review of model answers.

The initial analyzer correctly groups exact request/status/answer triples for
review, retains their complete private observation mapping, and never merges
answers to distinct requests. Packets omit model, policy, timings, repetitions,
actual supplied evidence, raw citations and condition mapping. Both review
packets use the same opaque IDs with independently shuffled presentation order.
Judgments must uniquely cover every group before quality analysis. That rule
makes the reviewed success-rate denominator all observed attempts, including
technical failures; missing scheduled attempts are reported separately.

Paired differences match request and repetition within a physical generator.
The analyzer averages the three paired differences within request, then
resamples eight whole scenario clusters with replacement. Shared draws retain
all request categories and all policy contrasts. This matches the protocol's
dependence model; repeated timing runs do not create independent quality tasks.
Intervals remain descriptive with only eight scenario clusters.

The measurement definitions correctly separate eligible-corpus inspection,
bounded source candidates, final retrieval and supplied evidence. Empty
relevant evidence produces undefined coverage, rather than a vacuous 100%.
Unnecessary-access denominators include only authorized no-memory-needed
requests. Selection, real retrieval, generation and validation use disjoint
stage fields; nested model loading/prefill/decode are diagnostics. Session
energy explicitly includes background power without idle subtraction.

Prospective review requests sent to the author:

- Reject `appropriate_abstention` on self-contained general tasks as well as
  known authorized personal tasks, and require abstention labels to set the
  abstention flag. This prevents an inconsistent reviewer label from bypassing
  the common success rubric.
- When averaging metrics across paired repetitions, discover keys from the
  union of all paired repetitions, not only the first available repetition.
- Give every authorized blinded packet the same full eligible active-profile
  truth background without IDs, while retaining the required requested claims
  in its rubric. Otherwise a true extra personal fact can be incorrectly
  labeled false/unsupported merely because it is not among requested IDs.
  Exclude superseded, deleted, expired and other-profile values from that
  background. Denied requests receive no authorized background. This background
  is identical across policies and never describes actual supplied evidence.
  Existing rubric prohibitions on unsolicited personal disclosure still apply.

Semantic unsupported-claim judgments against common truth references differ
from runtime-evidence grounding. A fact that happens to be correct without
supplied evidence is not a semantic error, but requires a separate grounding
diagnostic. The report must preserve that distinction.
