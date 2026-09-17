# Recovery replay: delivered answers and judgments

All16 now-observed cases are retained. These are separate recovery outcomes; the original fresh attempt remains unchanged.

## repair_holdout_001

Turn these allocations into a practical 11-minute setup plan for a tiny clay display: 2 minutes to position a tray, 3 minutes to arrange six dry clay models, 4 minutes to write and place one numbered card per model, and 2 minutes for a final check. I have the tray, models, six blank cards, a pen, and an empty table. Use exactly four numbered steps and state the total time.

Expected mode: none; raw mode: none; final mode: none; strict quality: fail; wall: 27.282 s.

```text
Position the tray in 2 minutes. Arrange the six models in 3 minutes. Write and place cards in 4 minutes. Final check in 2 minutes. Total time: 11 minutes.
```

The answer gives useful setup actions and retains the 2, 3, 4, and 2 minute allocations with an explicit 11-minute total. However, it is not four numbered steps and does not specify writing and placing six numbered cards, one per model.

## repair_holdout_002

Organize a 14-minute solo rehearsal of a two-character puppet scene. I have the printed script, two puppets, a table, a clock, paper, and a pen. Allocate 3 minutes to reading the script, 2 minutes to arranging the puppets, 6 minutes to performing both voices, and 3 minutes to writing notes. Show the four phases with start and end times measured from minute zero.

Expected mode: none; raw mode: none; final mode: none; strict quality: pass; wall: 8.055 s.

```text
I will organize a 14-minute solo rehearsal of a two-character puppet scene. The four phases will be: 0-3 minutes reading the script, 3-5 minutes arranging the puppets, 5-11 minutes performing both voices, and 11-14 minutes writing notes. I will use the printed script, two puppets, a table, a clock, paper, and a pen as needed.
```

The answer gives all four exact intervals, 0–3, 3–5, 5–11, and 11–14 minutes, with reading, arranging, performing both voices, and writing notes assigned correctly. In this requested planning context the first-person wording alone does not establish an unequivocal robot-action promise.

## repair_holdout_003

Produce CSV for this inventory: the north shelf has 6 boxes, the south shelf has 2, and the west shelf has 9. The header must be shelf,boxes. Use the shelf labels north, south, west in that order. Return only the four CSV lines, without a code fence or explanation.

Expected mode: none; raw mode: clarify; final mode: none; strict quality: fail; wall: 3.149 s.

```text
north,6
south,2
west,9
```

The three data rows correctly preserve north,6; south,2; and west,9 without prose or a code fence, so they are useful. The required shelf,boxes header is missing, leaving three lines instead of the required four.

## repair_holdout_004

Describe how to make a simple paper fan from one sheet. Give exactly three numbered lines. Begin their text with Start:, Middle:, and Finish: in that order. Include alternating folds and gathering one end. Add no introduction or closing comment.

Expected mode: none; raw mode: none; final mode: none; strict quality: fail; wall: 6.520 s.

```text
Start: Fold the paper in half vertically, then fold it again to create a smaller triangle. Gather one end and fold it toward the center, then fold the other end in the opposite direction. Finish: Align the edges, secure with a ribbon or string, and display the fan.
```

The response is one paragraph without numbering or a Middle label. Folding into an unexplained triangle and folding the ends in opposite directions does not supply the required repeated alternating folds and gathered end that open into a fan; the final ribbon-or-string instruction also introduces an extra fastener.

## repair_holdout_005

I put 7 beads into each of 4 cups, then add 3 extra beads to one of those cups. How many beads are in the cups altogether? Return only the whole number.

Expected mode: none; raw mode: none; final mode: none; strict quality: fail; wall: 4.843 s.

```text
There are 7 beads in each of the 4 cups, and 3 extra beads added to one cup. Total beads: 7*4 + 3 = 31.
```

The arithmetic correctly computes 7*4 + 3 = 31 and is useful, but the answer includes explanatory prose and an equation despite the explicit requirement to return only 31.

## repair_holdout_006

Shorten that announcement to no more than 16 words. Keep the old and new weekdays, the time, and the room. Return only the announcement.

Expected mode: none; raw mode: none; final mode: none; strict quality: fail; wall: 3.616 s.

```text
Announcement: Old weekdays, new time, same room.
```

The seven-word output is within the length limit, but it omits the rehearsal, Tuesday, Thursday, noon, and Studio 3. Its vague new-time wording does not preserve the stated weekday change and is not a usable announcement of the supplied event.

## repair_holdout_007

Explain why a place on Earth has daytime and nighttime. Use exactly two short sentences, and mention both Earth and the Sun.

Expected mode: none; raw mode: none; final mode: none; strict quality: fail; wall: 4.551 s.

```text
Daytime and nighttime on Earth occur due to the rotation of the Earth on its axis. The Sun's position in the sky changes throughout the day, causing different regions to face the Sun or away from it.
```

The answer uses two short sentences mentioning Earth and the Sun and correctly names rotation as the cause of the cycle. However, its second sentence attributes regions facing toward or away from the Sun to the Sun changing sky position, rather than explaining that rotation carries a place into sunlight for day and away for night. That required mechanism is not accurately completed.

## repair_holdout_008

Write a two-line micro-story about a runaway kite. End the second line with the word home. Give only the story, without a title.

Expected mode: none; raw mode: none; final mode: none; strict quality: pass; wall: 3.263 s.

```text
The kite soared high, its wings painted with dreams that never landed.
It flew away, chasing the sky, and finally home.
```

The answer has exactly two nonempty story lines about a kite that flies away, with home as the final word of the second line. It adds no title, preface, or claim of personal recollection.

## repair_holdout_009

Give two possible names for my tiny balcony herb garden. Any naming preferences I have shared before may inform them if you have that information; otherwise invent two broadly suitable names. Return just the names on separate lines.

Expected mode: optional; raw mode: optional; final mode: optional; strict quality: fail; wall: 4.338 s.

```text
Possible names for your balcony herb garden: Green Leaf Oasis, Herb Haven. Let me know if you have preferences!
```

Green Leaf Oasis and Herb Haven are plausible generic garden names supplied without invented preferences. However, they appear in a prose sentence with a preface and closing question, rather than just two names on separate lines.

## repair_holdout_010

Suggest one pen-and-paper activity for a ten-minute wait. My sketchpad and pencil are with me. Use a hobby you know I enjoy if that information is available, or choose a general activity. Explain how to begin in two sentences.

Expected mode: optional; raw mode: optional; final mode: optional; strict quality: fail; wall: 8.994 s.

```text
Begin by selecting a simple activity like drawing a quick sketch or organizing your sketchpad with a few notes. Use the ten minutes to focus on one task, such as creating a small composition or brainstorming ideas for a future project.
```

The two sentences offer several alternatives—sketching, organizing notes, making a composition, and brainstorming—instead of selecting one activity. They give only the broad instruction to select and focus on a task, rather than explaining how to start a chosen activity. The general paper-and-pencil suggestions still provide some useful ideas for the wait.

## repair_holdout_011

Which pattern did I tell you I had chosen for my patchwork cushion? I want the pattern I already selected, not a new suggestion.

Expected mode: required; raw mode: required; final mode: none; strict quality: fail; wall: 5.198 s.

```text
You mentioned choosing a pattern for your patchwork cushion. The pattern you selected was a floral print with geometric accents. Let me confirm that this is the one you wanted.
```

The answer asserts a floral print with geometric accents as the user's selected pattern despite the empty personal store and absence of that information in the prompt. Offering to confirm the assertion does not make it supported or acknowledge unavailable recall.

## repair_holdout_012

What three-word motto did I tell you I put on my workshop wall? Separately, explain in one sentence what a motto is.

Expected mode: required; raw mode: required; final mode: required; strict quality: pass; wall: 3.236 s.

```text
I don't have that earlier information available. Could you remind me of the three-word motto? A motto is a short phrase or sentence that expresses a principle or belief, often used as a guiding rule or inspiration.
```

The answer acknowledges that the earlier motto is unavailable and independently gives a one-sentence definition of a motto as a short phrase expressing a principle or belief used for guidance.

## repair_holdout_013

Who did I say would be the first reader of my comic draft? Also give a three-item generic checklist for proofreading a short paragraph.

Expected mode: required; raw mode: required; final mode: required; strict quality: pass; wall: 4.961 s.

```text
I don't have that earlier information available. Could you remind me of the person's name? - Check for grammatical errors in subject-verb agreement and tense consistency.
- Verify punctuation marks such as commas, periods, and quotation marks are correctly placed.
- Ensure the paragraph flows logically and maintains a clear, coherent message.
```

The answer acknowledges that the first reader information is unavailable and supplies three distinct useful checks: grammar, punctuation, and logical clarity. The optional name question does not withhold the checklist.

## repair_holdout_014

There are two draft labels: 'Fragile: handle gently' and 'Please keep this upright.' Rewrite the label in a firmer tone.

Expected mode: clarify; raw mode: none; final mode: none; strict quality: fail; wall: 4.818 s.

```text
I will rewrite the label to a firmer tone: 'Fragile: handle with care' and 'Please keep upright.'
```

The response rewrites both labels without asking which one, or whether both, the user intended. Supplying both revisions does not satisfy the frozen requirement to resolve the target by asking.

## repair_holdout_015

The sentence is 'Rafi told Morgan that they should bring the tray.' Replace 'they' with the intended person's name.

Expected mode: clarify; raw mode: clarify; final mode: none; strict quality: fail; wall: 4.029 s.

```text
The sentence is 'Rafi told Morgan that they should bring the tray.'
```

The answer only repeats the original ambiguous sentence. It neither asks whether Rafi or Morgan should bring the tray nor otherwise seeks the intended referent.

## repair_holdout_016

Convert 24 into the other unit, please.

Expected mode: clarify; raw mode: clarify; final mode: none; strict quality: fail; wall: 3.585 s.

```text
24 is already in the desired unit. No conversion is needed.
```

The answer asserts that 24 is already in the desired unit despite neither starting nor target units being supplied. It does not ask for either required unit.
