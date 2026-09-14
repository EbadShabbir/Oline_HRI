# Matched-evidence paired generator results

240 primary attempts; two independent blinded assistant reviews, 8 adjudications. Independent human validation pending.

| Category | Both correct | Only small | Only large | Neither |
| --- | ---: | ---: | ---: | ---: |
| overall | 39 | 4 | 37 | 40 |
| routine_general | 11 | 1 | 11 | 7 |
| constrained_general | 1 | 2 | 15 | 12 |
| personal_recall | 19 | 0 | 5 | 6 |
| personal_temporal | 8 | 1 | 6 | 15 |

| Model | Correct / 120 | Mean s | Median s | p95 s | Preloading total s | Startup-amortized mean s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen3:0.6b | 43 | 0.767 | 0.725 | 1.586 | 54.128 | 1.218 |
| qwen3:1.7b | 76 | 3.932 | 2.909 | 9.144 | 132.060 | 5.032 |

## All paired answers

### cg07: both_correct

Choose a rug from these options. It must cost no more than 40 tokens, be washable, and be blue. Give the name and one sentence explaining the choice.

Evidence: ["Luma: blue, washable, 38 tokens. Nori: blue, not washable, 30 tokens. Selo: red, washable, 25 tokens."]

**qwen3:0.6b — complete**

Luma: blue, washable, 38 tokens. It costs no more than 40 tokens and is washable, so this is the best choice.

Selects only Luma and supplies its blue color, washability, and 38-token price with a one-sentence explanation.

**qwen3:1.7b — complete**

Luma: Name - Luma, Explanation - Luma is blue, washable, and costs 38 tokens, which is within the budget of 40 tokens.

Names only Luma and explains all three constraints in one sentence.

### pr02: both_correct

Where did I say I keep the spare shoelaces?

Evidence: ["You keep spare shoelaces in the blue tin inside the coat cupboard.", "Extra buttons are in a jar on the desk."]

**qwen3:0.6b — complete**

The spare shoelaces are kept in the blue tin inside the coat cupboard.

Correctly locates the shoelaces in the blue tin inside the coat cupboard.

**qwen3:1.7b — complete**

You kept the spare shoelaces in the blue tin inside the coat cupboard.

Correctly supplies the blue tin inside the coat cupboard.

### pr03: both_correct

Which day is my regular paper-folding group?

Evidence: ["Your paper-folding group meets on Wednesdays.", "Your neighbour attends a painting class on Mondays."]

**qwen3:0.6b — complete**

Wednesday

Correctly gives Wednesday.

**qwen3:1.7b — complete**

Wednesday

Correctly gives Wednesday.

### pr04: both_correct

Remind me of the name of my stuffed penguin.

Evidence: ["You named your stuffed penguin Peblet.", "Your ceramic owl is called Koro."]

**qwen3:0.6b — complete**

Peblet

Correctly recalls Peblet.

**qwen3:1.7b — complete**

Your stuffed penguin is named Peblet.

Correctly names Peblet.

### pr06: both_correct

Who lends me the wooden jigsaw puzzles?

Evidence: ["Your cousin Tavia lends you wooden jigsaw puzzles.", "Your friend Olen lends you magazines."]

**qwen3:0.6b — complete**

Your cousin Tavia lends you wooden jigsaw puzzles.

Correctly names cousin Tavia as the puzzle lender.

**qwen3:1.7b — complete**

Your cousin Tavia

Correctly names cousin Tavia.

### pr07: both_correct

What did I call the small balcony fern?

Evidence: ["You call the small balcony fern Ziglet.", "The large hallway plant has no recorded nickname."]

**qwen3:0.6b — complete**

Ziglet

Correctly gives Ziglet.

**qwen3:1.7b — complete**

You called the small balcony fern Ziglet.

Correctly recalls the fern name Ziglet.

### pr08: both_correct

Which room do I prefer for listening to audiobooks?

Evidence: ["You prefer listening to audiobooks in the sunroom.", "You do crossword puzzles in the kitchen."]

**qwen3:0.6b — complete**

sunroom

Correctly gives the sunroom.

**qwen3:1.7b — complete**

sunroom

Correctly gives the sunroom.

### pr09: both_correct

What two things did I ask to keep on the tray beside my armchair?

Evidence: ["You asked to keep a bookmark and a pencil on the tray beside your armchair.", "The remote control belongs in the wall pocket."]

**qwen3:0.6b — complete**

a bookmark and a pencil

Correctly gives the bookmark and pencil.

**qwen3:1.7b — complete**

Bookmark and pencil

Correctly gives the bookmark and pencil without adding the remote.

### pr10: both_correct

How many place mats are in my picnic set?

Evidence: ["Your picnic set contains six place mats.", "Your indoor dining set contains four place mats."]

**qwen3:0.6b — complete**

6

Correctly gives six picnic place mats.

**qwen3:1.7b — complete**

Your picnic set contains six place mats.

Correctly gives six picnic place mats.

### pr11: both_correct

Which scent do I prefer for the drawer sachets?

Evidence: ["You prefer cedar-scented drawer sachets.", "You dislike rose-scented sachets."]

**qwen3:0.6b — complete**

cedar-scented

Correctly gives cedar scent.

**qwen3:1.7b — complete**

Cedar-scented

Correctly gives cedar scent.

### pr12: both_correct

Where is the spare roll of wrapping paper now?

Evidence: ["On 4 August you stored the spare wrapping-paper roll behind the desk.", "On 9 August you moved that roll to the tall hallway basket, replacing its earlier location."]

**qwen3:0.6b — complete**

The spare roll of wrapping paper is now in the tall hallway basket.

Correctly gives the tall hallway basket as the current location.

**qwen3:1.7b — complete**

The spare roll of wrapping paper is now in the tall hallway basket.

Correctly gives the tall hallway basket as the replacement location.

### pr13: both_correct

What is my chosen name for the new knitting basket?

Evidence: ["You first called the new knitting basket Dotbox.", "You later corrected that name to Stitchnest; Stitchnest is the active name."]

**qwen3:0.6b — complete**

Stitchnest

Correctly supplies the active name Stitchnest.

**qwen3:1.7b — complete**

Stitchnest

Correctly gives the active basket name Stitchnest.

### pr15: both_correct

What did I choose to put on the front of my recipe folder?

Evidence: ["You chose a drawing of a pear for the front of your recipe folder.", "Your address book has a drawing of a kite."]

**qwen3:0.6b — complete**

A drawing of a pear

Correctly identifies the pear drawing for the recipe folder.

**qwen3:1.7b — complete**

You chose a drawing of a pear to put on the front of your recipe folder.

Correctly identifies the pear drawing.

### pr16: both_correct

Do I prefer background music or silence when doing a crossword?

Evidence: ["You prefer silence while doing crosswords.", "You enjoy background music while washing dishes."]

**qwen3:0.6b — complete**

silence

Correctly gives silence for crosswords.

**qwen3:1.7b — complete**

You prefer silence while doing crosswords, so background music is not preferred.

Correctly identifies silence as the crossword preference.

### pr17: both_correct

What material did I want for the replacement doormat?

Evidence: ["Your confirmed choice for the replacement doormat is coir.", "You chose cotton for the bathroom mat."]

**qwen3:0.6b — complete**

coir

Correctly gives coir.

**qwen3:1.7b — complete**

You wanted a coir doormat.

Correctly identifies coir as the wanted doormat material.

### pr18: both_correct

What time is my weekly call with my friend Siven?

Evidence: ["Your weekly call with Siven is at 18:40.", "Your weekly call with Daro is at 17:15."]

**qwen3:0.6b — complete**

18:40

Correctly gives 18:40.

**qwen3:1.7b — complete**

Your weekly call with Siven is at 18:40.

Correctly gives the Siven call time as 18:40.

### pr20: both_correct

What is the title of the poem I wanted to read to Elya?

Evidence: ["You wanted to read a short poem to Elya.", "The poem title and author were not recorded."]

**qwen3:0.6b — appropriate_abstention**

The title of the poem is not recorded.

Correctly acknowledges the unrecorded poem title.

**qwen3:1.7b — appropriate_abstention**

The title of the poem cannot be determined from the provided evidence.

Correctly acknowledges that the poem title cannot be determined.

### pr22: both_correct

Which bus route did I plan to take to the pottery market?

Evidence: ["You planned to visit the pottery market by bus.", "No bus route number or route name is recorded."]

**qwen3:0.6b — appropriate_abstention**

No evidence provided.

Acknowledges the absence of evidence for the requested bus route without inventing one.

**qwen3:1.7b — appropriate_abstention**

The information provided does not specify the bus route number or name planned for the trip to the pottery market.

Correctly identifies the unrecorded bus route number or name.

### pr23: both_correct

What fabric is my striped apron made from?

Evidence: ["Your apron has green and white stripes.", "The apron fabric is not specified."]

**qwen3:0.6b — appropriate_abstention**

The fabric is not specified.

Correctly acknowledges the unspecified apron fabric.

**qwen3:1.7b — appropriate_abstention**

The fabric of your striped apron is not specified in the provided evidence.

Correctly acknowledges that the apron fabric is unspecified.

### pr24: both_correct

What nickname does my friend Meran use for me?

Evidence: ["Meran is your friend from the model-boat club.", "No nickname Meran uses for you is recorded."]

**qwen3:0.6b — appropriate_abstention**

No nickname is recorded.

Correctly states that no nickname is recorded.

**qwen3:1.7b — appropriate_abstention**

The nickname Meran uses for you is not recorded.

Correctly says Meran’s nickname for the user is unrecorded.

### pt01: both_correct

How did my preferred place for breakfast change, and what is the current preference?

Evidence: ["On 2 July you preferred breakfast on the balcony.", "On 12 July you changed your breakfast preference to the kitchen nook, replacing the balcony preference."]

**qwen3:0.6b — complete**

Your preferred place for breakfast changed from the balcony on 12 July to the kitchen nook. The current preference is the kitchen nook.

Correctly describes the change from balcony to kitchen nook and identifies the current preference.

**qwen3:1.7b — complete**

Your preferred place for breakfast changed from the balcony to the kitchen nook. The current preference is the kitchen nook.

Correctly states the balcony-to-kitchen-nook change and current kitchen nook preference.

### pt06: both_correct

What changed about my Tuesday craft routine, and which parts stayed the same?

Evidence: ["Your old Tuesday routine was knitting at 10:00 in the lounge.", "Your updated Tuesday routine is paper cutting at 10:00 in the lounge, replacing the old routine."]

**qwen3:0.6b — complete**

The routine changed: your old Tuesday routine was knitting at 10:00 in the lounge, and your updated routine is paper cutting at 10:00 in the lounge.

Correctly contrasts knitting with paper cutting while retaining 10:00 and the lounge for both routines.

**qwen3:1.7b — complete**

Your Tuesday craft routine was replaced. The old routine was knitting at 10:00 in the lounge, but the updated routine is paper cutting at 10:00 in the lounge. The specific activity has changed, but the time and location remain the same.

Correctly identifies knitting changing to paper cutting while 10:00 and the lounge stay unchanged.

### pt09: both_correct

Summarise my changing seat choice for film night, distinguishing my first choice, temporary choice and current choice.

Evidence: ["On 1 February you chose the armchair for film night.", "On 5 February you temporarily switched to the sofa.", "On 8 February you changed to the window bench, replacing the sofa; the bench remains your current choice."]

**qwen3:0.6b — complete**

On 1 February, you chose the armchair for film night. On 5 February, you temporarily switched to the sofa. On 8 February, you changed to the window bench, replacing the sofa; the bench remains your current choice.

Correctly distinguishes the initial armchair, temporary sofa, and current window bench.

**qwen3:1.7b — complete**

Your first choice was the armchair, your temporary choice was the sofa, and your current choice is the window bench.

Correctly distinguishes first armchair, temporary sofa, and current window bench.

### pt10: both_correct

For my next craft visit, combine my current travel choice with the two supplies I said I would bring.

Evidence: ["You initially planned to walk to the next craft visit.", "You changed that plan to travel by tram, replacing walking.", "For that visit you agreed to bring felt sheets and wooden beads."]

**qwen3:0.6b — complete**

For my next craft visit, combine your current travel choice with the supplies you agreed to bring. You initially planned to walk, but changed to a tram, and for that visit, you agreed to bring felt sheets and wooden beads.

Correctly gives the replacement tram plan and the two agreed supplies despite an unnecessary introductory instruction.

**qwen3:1.7b — complete**

For your next craft visit, you will travel by tram and bring felt sheets and wooden beads.

Correctly combines tram travel with felt sheets and wooden beads.

### pt11: both_correct

Did my frame-painting session overlap the parcel collection window? If so, give the overlap interval and its duration.

Evidence: ["Your frame-painting session ran 11:00-11:40 on 13 June.", "Your parcel collection window was 11:25-12:00 on the same day."]

**qwen3:0.6b — complete**

Yes, the frame-painting session and parcel collection window overlapped. The overlap interval was 11:25-11:40 on the same day, with a duration of 15 minutes.

Correctly gives overlap, 11:25-11:40, and fifteen minutes.

**qwen3:1.7b — complete**

Yes, the frame-painting session overlapped the parcel collection window. The overlap interval was 11:25-11:40, and the duration was 15 minutes.

Correctly reports overlap from 11:25 to 11:40 lasting fifteen minutes.

### pt14: both_correct

What should my picnic note say about the current meeting place and the item assigned to me?

Evidence: ["The picnic was originally to meet at Willow Arch.", "The group moved the same picnic meeting to Stone Steps, replacing Willow Arch.", "You agreed to bring the checked blanket; Nevi agreed to bring cups."]

**qwen3:0.6b — complete**

The current meeting place is Stone Steps, and you should include the checked blanket as part of your picnic note.

Correctly supplies Stone Steps and the user’s checked blanket assignment.

**qwen3:1.7b — complete**

Your picnic note should mention that the meeting place has been moved from Willow Arch to Stone Steps, and you are responsible for bringing the checked blanket.

Correctly identifies Stone Steps as current and the checked blanket as the user’s assignment.

### pt19: both_correct

How many days did I spend making the patchwork cover?

Evidence: ["You started the patchwork cover on 6 July 2026.", "You later said it was finished, but no completion date or duration was recorded."]

**qwen3:0.6b — appropriate_abstention**

The evidence provided does not include a completion date or duration, so it's uncertain how many days I spent making the patchwork cover.

Correctly explains that missing completion date or duration prevents calculating days spent.

**qwen3:1.7b — appropriate_abstention**

The exact number of days spent making the patchwork cover cannot be determined with the provided information.

Correctly states that the supplied information cannot determine the duration and invents nothing. The question does not require restating the start date or naming the missing completion field; the explanation of insufficient information adequately supports abstention.

### pt28: both_correct

Summarise my latest plan for carrying things to the board-game visit.

Evidence: ["You originally planned to carry a red bag to the visit.", "Current confirmed revision A: use the grey tote instead.", "Equally current revision B: use the striped basket instead; neither revision overrides the other.", "Your assigned items remain a game board and score pad."]

**qwen3:0.6b — appropriate_uncertainty**

Your latest plan includes using a grey tote instead of a red bag, with a striped basket equally current, and your assigned items remain a game board and score pad.

Reports both carrier revisions as equally current and supplies the agreed game board and score pad.

**qwen3:1.7b — appropriate_uncertainty**

Your latest plan for carrying things to the board-game visit involves using a grey tote, with an equally current alternative of a striped basket. The original plan was to use a red bag, but this has been revised to either the grey tote or the striped basket, with neither revision overriding the other. Your assigned items remain a game board and score pad.

Reports the equally current tote and basket alternatives without priority and supplies both agreed items.

### rg01: both_correct

Why does a wet cloth usually dry faster when spread out than when left in a ball?

Evidence: []

**qwen3:0.6b — complete**

Because spreading the cloth increases surface area, allowing more water to evaporate more efficiently.

Correctly connects greater exposed surface with faster evaporation.

**qwen3:1.7b — complete**

A wet cloth dries faster when spread out because it increases the surface area exposed to air, allowing water to evaporate more quickly. When the cloth is in a ball, the surface area is reduced, leading to slower evaporation.

Correctly explains exposed wet surface and faster evaporation.

### rg02: both_correct

A kitchen timer counts down from 12 minutes. What does its display reaching zero tell me?

Evidence: []

**qwen3:0.6b — complete**

The display reaching zero indicates the timer has completed its countdown, signaling the end of the specified time period.

Correctly says the selected countdown interval has finished, without claiming food is cooked.

**qwen3:1.7b — complete**

The display reaching zero indicates that the 12-minute timer has completed its countdown.

Correctly states the selected twelve-minute countdown has finished.

### rg05: both_correct

Explain what a reminder can do that a plain note on paper cannot automatically do.

Evidence: []

**qwen3:0.6b — complete**

A reminder can automatically schedule tasks, set reminders for events, or trigger actions based on specific conditions, while a plain note on paper is limited to simple information storage and communication.

Contrasts automatic event reminders or triggered actions with a passive paper note.

**qwen3:1.7b — complete**

A reminder can set a specific time or date to notify you about an event, whereas a plain note on paper cannot automatically do this. It can also be set to repeat periodically or alert you via multiple channels (e.g., sound, email, app notification).

Correctly explains automatic timed notification and contrasts it with a paper note.

### rg06: both_correct

Why is it easier to find things in boxes with descriptive labels?

Evidence: []

**qwen3:0.6b — complete**

Because descriptive labels help identify items, making it easier to find them in boxes.

Connects descriptive labels to identifying the items in boxes directly.

**qwen3:1.7b — complete**

Descriptive labels on boxes help users quickly identify the contents, making it easier to find items by providing visual cues and reducing the need for additional information.

Explains that labels reveal contents so the right box can be identified directly.

### rg08: both_correct

What does it mean to do two chores in parallel rather than one after the other?

Evidence: []

**qwen3:0.6b — complete**

Doing two chores in parallel means completing both tasks simultaneously rather than sequentially. This approach can save time and improve efficiency, especially when tasks are related or can be done at the same time.

Correctly explains overlapping simultaneous work versus sequential chores.

**qwen3:1.7b — complete**

Doing two chores in parallel means performing them at the same time, rather than one after the other. This allows for simultaneous completion of tasks, which can save time and increase efficiency.

Clearly contrasts simultaneous chores with performing them one after another.

### rg12: both_correct

When measuring a table for a cover, why do length and width both matter?

Evidence: []

**qwen3:0.6b — complete**

Length and width both matter when measuring a table for a cover to ensure accurate dimensions for proper fit and functionality.

Connects both dimensions to obtaining a properly fitting table cover.

**qwen3:1.7b — complete**

When measuring a table for a cover, both length and width matter because the cover needs to fit precisely to the table's dimensions. The length determines the horizontal size, and the width determines the vertical size, ensuring the cover is the correct size and shape to securely cover the table.

Explains that both tabletop dimensions determine whether the cover fits fully.

### rg13: both_correct

Which weighs more: one kilogram of towels or one kilogram of wooden blocks?

Evidence: []

**qwen3:0.6b — complete**

One kilogram of towels weighs the same as one kilogram of wooden blocks.

Correctly states that the two one-kilogram quantities weigh the same.

**qwen3:1.7b — complete**

They weigh the same, both are 1 kilogram.

Correctly identifies equal one-kilogram weights.

### rg14: both_correct

What is the difference between a reusable shopping bag and a single-use bag?

Evidence: []

**qwen3:0.6b — complete**

A reusable shopping bag is designed to be used multiple times, while a single-use bag is intended for one use only.

Correctly distinguishes intended repeated use from intended single use.

**qwen3:1.7b — complete**

A reusable shopping bag is made from materials that can be used multiple times, while a single-use bag is designed for one-time use and is typically not recycled. Reusable bags are more sustainable and reduce waste, whereas single-use bags contribute to environmental pollution.

Correctly distinguishes repeated-use design from one-time-use design and gives broadly plausible waste implications.

### rg16: both_correct

In a checklist, what does an unchecked box usually mean?

Evidence: []

**qwen3:0.6b — complete**

An unchecked box in a checklist typically means that the item is not marked as completed or verified.

Correctly describes an item not marked complete or verified without claiming it never happened.

**qwen3:1.7b — complete**

An unchecked box in a checklist usually means that the item has not been completed or is not yet selected.

Describes an unchecked item as usually unfinished or unselected without claiming the action certainly never happened.

### rg20: both_correct

Two identical boxes each hold eight cups. How many cups can they hold together?

Evidence: []

**qwen3:0.6b — complete**

16

Correctly gives sixteen cups.

**qwen3:1.7b — complete**

They can hold 16 cups together.

Correctly gives sixteen cups.

### rg23: both_correct

What is the difference between estimating a shelf length and measuring it?

Evidence: []

**qwen3:0.6b — complete**

Estimating a shelf length involves using a method to guess the space, while measuring involves using a tool to determine the exact length.

Correctly contrasts guessing an approximate length with using a measuring tool.

**qwen3:1.7b — complete**

Estimating a shelf length involves using approximate measurements based on visual or contextual cues, while measuring it involves using precise tools and methods to determine the exact length.

Correctly contrasts approximation with use of measuring tools for greater precision.

### cg01: neither_correct

Suggest a quiet ten-minute indoor break. Give exactly three numbered steps, no screens, and include stretching and a drink of water.

Evidence: []

**qwen3:0.6b — partial**

1. Sit in a comfortable chair and stretch your arms and legs. 2. Take a deep breath and close your eyes. 3. Drink a glass of water to stay hydrated.

Gives three numbered quiet indoor steps with stretching and water, but no timing establishes a ten-minute total.

**qwen3:1.7b — partial**

1. Sit comfortably on a chair or floor and slowly stretch your shoulders and back by raising them slowly into a triangle position. 2. Take a few deep breaths and focus on your breath to relax your body. 3. Drink a glass of water while sitting in a quiet place to stay hydrated.

Gives three numbered quiet steps with stretching and water but no durations establish the required ten-minute total.

### cg02: neither_correct

Plan packing these items into two bags: a vase, a book and a towel. The vase must be wrapped in the towel; the book must be in the other bag. Name each bag and its contents, in two lines.

Evidence: []

**qwen3:0.6b — partial**

Bag 1: Vase wrapped in towel, Book in the other bag. Bag 2: Book, towel.

Places a wrapped vase and separate book but also assigns the towel to the second bag and fails the two-line format.

**qwen3:1.7b — incorrect**

Bag 1: Vase and book
Bag 2: Towel

Uses two named lines but packs the book with the vase and separates the towel, violating both packing requirements.

### cg03: neither_correct

Write a friendly message cancelling a chess visit tomorrow. Use exactly two sentences, give no excuse, and offer Saturday instead.

Evidence: []

**qwen3:0.6b — partial**

Hi there! I hope you're having a great day. I'm sorry we can't make your chess visit tomorrow. Would you like to have a meeting on Saturday instead?

Friendly cancellation offers Saturday without an excuse, but has four sentences instead of two.

**qwen3:1.7b — partial**

Hi there! I'd like to cancel my chess visit tomorrow. Let me know if you'd like to reschedule to Saturday instead.

Friendly cancellation offers Saturday without an excuse, but the greeting makes three sentences instead of two.

### cg06: neither_correct

Organise three chores beginning at 14:00: sweep for 10 minutes, fold towels for 15, and water pots for 5. Do them one at a time, back-to-back with no gaps, sweep first and water last; give each start and finish time.

Evidence: []

**qwen3:0.6b — partial**

14:00 - 14:10: Sweep; 14:11 - 14:16: Fold towels; 14:17 - 14:22: Water pots

Gets the sweep interval and chore order right but gives only five minutes to folding and inserts forbidden gaps.

**qwen3:1.7b — incorrect**

Sweep from 14:00:00 to 14:00:10, fold towels from 14:00:10 to 14:00:25, water pots from 14:00:25 to 14:00:30.

Schedules ten, fifteen, and five seconds rather than the requested minutes, yielding wrong finish times.

### cg08: neither_correct

Turn this note into exactly three bullets in the same order, using a verb to start each bullet: "The cups need washing. Then the mat needs shaking outside. Finally the counter needs wiping."

Evidence: []

**qwen3:0.6b — partial**

The cups need washing. Then the mat needs shaking outside. Finally the counter needs wiping.

Retains the three tasks in order but supplies no bullets and does not start them with action verbs.

**qwen3:1.7b — partial**

the cups need washing
the mat needs shaking outside
the counter needs wiping

Keeps the tasks in order but uses neither bullets nor verb-first wording.

### cg12: neither_correct

Order these jobs: put books on the shelf, dust the empty shelf, remove the books. Use a single sentence with "first", "then" and "finally".

Evidence: []

**qwen3:0.6b — incorrect**

first, put books on the shelf, then dust the empty shelf, finally remove the books.

Uses the requested connective words in one sentence but reverses the remove-dust-return job order.

**qwen3:1.7b — incorrect**

First, put books on the shelf. Then, dust the empty shelf. Finally, remove the books.

Reverses the required remove-dust-return sequence and uses three sentences instead of one.

### cg13: neither_correct

Divide 18 biscuits equally among three guests and save none. State biscuits per guest and verify the total in one sentence.

Evidence: []

**qwen3:0.6b — incorrect**

18 biscuits divided equally among 6 guests, with each guest receiving 3 biscuits.

Changes three guests to six and gives three biscuits each instead of six.

**qwen3:1.7b — partial**

Each guest receives 6 biscuits. The total number of biscuits is 18, which is evenly divided among the three guests.

Correctly divides all eighteen biscuits into six per guest but fails the requested one-sentence answer and explicit arithmetic verification.

### cg15: neither_correct

Compare hanging and folding clean shirts in exactly two bullets, one for each method. Give one practical benefit per method and do not claim either is always best.

Evidence: []

**qwen3:0.6b — partial**

Hanging clean shirts: 1. Keeps fabric fresh and free from stains. 2. Reduces the need for frequent washing. Folding clean shirts: 1. Saves space and reduces laundry time. 2. Keeps fabric clean and free from wrinkles.

Includes a valid folding space benefit but adds unsupported stain, washing, and wrinkle claims and fails the two-bullet, one-benefit format.

**qwen3:1.7b — partial**

Hanging clean shirts allows for better air circulation and prevents fabric from becoming too stiff, while folding clean shirts makes them easier to handle and store. Hanging provides a more natural drying process, and folding is more convenient for storage.

Discusses both methods without a universal winner, but omits the required two bullets and gives multiple benefits. The categorical claim that hanging prevents fabric stiffness is unwarranted, so the unsupported-claim flag is true.

### cg18: neither_correct

Choose the earliest fictional shuttle that leaves at or after 09:20 and arrives by 10:00. Name it and its departure and arrival times.

Evidence: ["Ash leaves 09:10, arrives 09:35. Birch leaves 09:25, arrives 09:55. Cedar leaves 09:40, arrives 10:05."]

**qwen3:0.6b — incorrect**

Cedar, 09:40, 10:05

Selects Cedar, whose 10:05 arrival misses the deadline; Birch at 09:25-09:55 is required.

**qwen3:1.7b — incorrect**

The earliest fictional shuttle is Cedar. It leaves at 09:40 and arrives by 10:05.

Falsely calls Cedar earliest and selects its too-late 10:05 arrival instead of qualifying Birch.

### cg22: neither_correct

Pick two activities for a rainy indoor afternoon from knitting, kite flying, reading and garden digging. Neither may require going outside. Give exactly two bullets and one short reason for each.

Evidence: []

**qwen3:0.6b — incorrect**

1. Knitting: Use a knitting mat and follow the instructions to create a pattern. 2. Kite flying: Fly a kite using a kite string and a safe location indoors. Reason: Neither activity requires going outside, and both are suitable for an indoor afternoon.

Chooses kite flying instead of reading and claims ordinary kite flying needs no outdoor access; also lacks two bullets and separate reasons.

**qwen3:1.7b — incorrect**

1. Reading
   Reason: It does not require going outside and can be done comfortably indoors.
2. Garden digging
   Reason: It can be done indoors and is a relaxing activity that does not require outside access.

Chooses garden digging instead of knitting and falsely describes it as requiring no outdoor access; uses numbered entries rather than two bullets.

### cg25: neither_correct

Find a lamp that is cordless, costs at most 30 tokens, and provides warm light. Name a qualifying lamp only if every condition is established; otherwise identify the missing fact in one sentence.

Evidence: ["Meka lamp: cordless, 24 tokens; light colour not specified. Filo lamp: corded, 20 tokens, warm light."]

**qwen3:0.6b — incorrect**

Meka lamp is cordless, costs at most 30 tokens, and provides warm light.

Certifies Meka by inventing warm light although its light color is unspecified.

**qwen3:1.7b — incorrect**

Meka lamp

Certifies Meka despite its unrecorded light color and omits the missing fact.

### cg28: neither_correct

Give the room and start time for the fictional Kestrel puzzle club in one sentence. If either field conflicts, report both listed alternatives and do not choose between them.

Evidence: ["Current listing A: Kestrel puzzle club, room 2, 16:00.", "Equally authoritative current listing B: Kestrel puzzle club, room 2, 16:30; no replacement is indicated."]

**qwen3:0.6b — incorrect**

Kestrel puzzle club, room 2, 16:30.

Room 2 is correct, but presenting 16:30 as the sole start time wrongly resolves equally authoritative conflicting listings. This is an unsupported central conclusion, not merely an omitted detail.

**qwen3:1.7b — partial**

The fictional Kestrel puzzle club is scheduled for room 2 starting at 16:00. Alternatively, it is also scheduled for room 2 starting at 16:30, with no replacement indicated.

Gives room 2 and both unresolved start alternatives, but uses two sentences instead of one.

### pr25: neither_correct

Where do I currently keep the embroidery hoop?

Evidence: ["Current confirmed memory: your embroidery hoop is in the wicker trunk.", "Another current confirmed memory: the same hoop is in the low cabinet. The trunk and cabinet are separate places, neither inside the other. Neither memory supersedes the other."]

**qwen3:0.6b — incorrect**

The embroidery hoop is currently in the wicker trunk, as confirmed by evidence. The low cabinet is separate and unrelated.

Resolves the hoop location to the trunk and dismisses an equally current conflicting cabinet memory.

**qwen3:1.7b — incorrect**

You currently keep the embroidery hoop in the wicker trunk.

Chooses the wicker trunk despite the equally current conflicting low cabinet memory.

### pr26: neither_correct

What is my preferred colour for the new curtain tiebacks?

Evidence: ["Active confirmed preference: teal curtain tiebacks.", "Equally current confirmed preference for the same tiebacks: rust. No correction or priority is recorded."]

**qwen3:0.6b — incorrect**

teal

Chooses teal despite the unresolved equally current rust preference.

**qwen3:1.7b — incorrect**

Your preferred colour for the new curtain tiebacks is teal.

Chooses teal without acknowledging the equally current rust preference.

### pr27: neither_correct

Who is bringing my folding stool back?

Evidence: ["Confirmed current note: your friend Nolvi alone is bringing your folding stool back, not Peren.", "Equally current confirmed note: your cousin Peren alone is bringing the same stool back, not Nolvi. No note overrides the other."]

**qwen3:0.6b — incorrect**

Peren

Chooses Peren despite the equally current conflicting Nolvi assignment.

**qwen3:1.7b — incorrect**

Your cousin Peren is bringing your folding stool back.

Definitively names Peren despite conflicting exclusive return assignments to Nolvi and Peren.

### pr28: neither_correct

What time is my next window-box delivery?

Evidence: ["Active confirmed delivery note: your next window-box delivery is at 11:20.", "Another equally current confirmed note for that same delivery says 13:10. Neither is marked corrected."]

**qwen3:0.6b — incorrect**

11:20

Chooses 11:20 without acknowledging the equally current 13:10 note.

**qwen3:1.7b — incorrect**

Your next window-box delivery is scheduled for 11:20.

Gives 11:20 as settled and omits the equally current 13:10 delivery note.

### pr29: neither_correct

How many napkins are in my blue picnic pouch?

Evidence: ["Current inventory: the blue picnic pouch contains three napkins.", "Equally current inventory of the same pouch: it contains five napkins. No intervening change or priority is recorded."]

**qwen3:0.6b — incorrect**

5 napkins

Chooses five napkins despite equally current three-versus-five inventories.

**qwen3:1.7b — incorrect**

Your blue picnic pouch contains three napkins.

Chooses three napkins despite equally current conflicting three- and five-napkin inventories.

### pr30: neither_correct

What name did I finally choose for my new tabletop game?

Evidence: ["Current confirmed name for your new tabletop game: Pebble Path.", "Equally current confirmed name for the same game: Lantern Loop. Neither is a correction or a draft."]

**qwen3:0.6b — incorrect**

Pebble Path.

Chooses Pebble Path as final despite the equally current Lantern Loop record.

**qwen3:1.7b — incorrect**

You finally chose the name 'Pebble Path' for your new tabletop game.

Selects Pebble Path as final despite an equally current Lantern Loop record.

### pt02: neither_correct

How many days passed between my buying the mosaic kit and finishing it?

Evidence: ["You bought a mosaic kit on 3 June 2026.", "You finished that kit on 11 June 2026."]

**qwen3:0.6b — incorrect**

5 days

Gives five elapsed days instead of eight.

**qwen3:1.7b — incorrect**

5 days

Gives five elapsed days instead of eight between 3 and 11 June.

### pt05: neither_correct

How long did my visit with Faryn last, and how long before my radio programme began did it finish?

Evidence: ["Your visit with Faryn ran from 14:10 to 15:00 on 22 March.", "Your radio programme began at 15:20 that day."]

**qwen3:0.6b — incorrect**

The visit with Faryn lasted 40 minutes, and it began 40 minutes before the radio programme began.

Both timing claims are wrong: the visit lasted fifty minutes and finished twenty minutes before the programme.

**qwen3:1.7b — partial**

Your visit with Faryn lasted 50 minutes. It finished 50 minutes before your radio programme began.

Correctly gives the fifty-minute visit but incorrectly gives a fifty-minute gap instead of twenty.

### pt07: neither_correct

Which came first, my visit to the puppet show or my purchase of the wool scarf, and how far apart were they?

Evidence: ["You visited the puppet show on 27 January 2026.", "You bought the wool scarf on 30 January 2026."]

**qwen3:0.6b — partial**

27 January 2026, 30 January 2026

Provides the two supported dates but does not name which event came first or state the three-day gap.

**qwen3:1.7b — partial**

Your visit to the puppet show came first. They occurred on 27 January 2026 for the show, and the purchase of the wool scarf occurred on 30 January 2026, which is later than the visit.

Correctly identifies the puppet show as first and gives both dates but does not state the requested three-day interval.

### pt08: neither_correct

Which of the recorded gifts did I receive after the lantern walk but before the garden lunch?

Evidence: ["You received a puzzle on 2 August 2026.", "The lantern walk was on 4 August 2026.", "You received a bookmark on 6 August 2026.", "The garden lunch was on 9 August 2026.", "You received a mug on 10 August 2026."]

**qwen3:0.6b — incorrect**

The mug was received on 10 August 2026.

Selects the mug instead of the bookmark. Its receipt date is supported, but offering it as the answer asserts that the user received it before the garden lunch, contradicting the record; the central selection and both unsupported-claim flags therefore fail.

**qwen3:1.7b — partial**

The bookmark received on 6 August 2026 and the mug received on 10 August 2026.

Includes the qualifying bookmark but also the mug, which arrived after the garden lunch. Although both receipt dates are supported, selecting the mug asserts that the user received it within the requested interval, a contradicted personal claim.

### pt12: neither_correct

What were my first and most recent completed jigsaws, and how many did I finish in between?

Evidence: ["You finished Harbour Lights on 2 December 2025.", "You finished Meadow Gate on 5 December 2025.", "You finished Copper Train on 8 December 2025.", "You finished Moonlit Orchard on 13 December 2025. These are all your completed jigsaws in the record."]

**qwen3:0.6b — incorrect**

2 December 2025 and 8 December 2025, 6 completed jigsaws in between.

Gives wrong latest date and invents six intervening jigsaws; omits both requested names.

**qwen3:1.7b — partial**

Your first completed jigsaw was 'Harbor Lights' on 2 December 2025, and your most recent was 'Moonlit Orchard' on 13 December 2025. You completed 4 jigsaws in total between these dates.

Identifies both endpoint jigsaws, with a harmless spelling variant, but gives the four-item inclusive total instead of two intervening completions.

### pt13: neither_correct

How much earlier is my revised weekly call, and with whom is it?

Evidence: ["Your weekly call with your friend Brena used to start at 19:10.", "You and Brena moved that same weekly call to 18:35, replacing 19:10."]

**qwen3:0.6b — partial**

The revised weekly call started at 18:35, which is 1 hour earlier than the original 19:10 call with Brena.

Correctly names Brena and 18:35 but falsely describes the shift as one hour instead of thirty-five minutes.

**qwen3:1.7b — partial**

The revised weekly call is 35 seconds earlier than the original schedule and is with Brena.

Correctly names Brena but gives thirty-five seconds instead of thirty-five minutes earlier.

### pt16: neither_correct

Which person had my fabric scissors immediately before I got them back?

Evidence: ["On 3 April you lent your fabric scissors to Elvor.", "On 5 April Elvor passed them to Minae with your permission.", "On 8 April Minae returned those scissors to you."]

**qwen3:0.6b — incorrect**

Elvor

Names Elvor although Minae held the scissors immediately before return.

**qwen3:1.7b — incorrect**

Elvor

Names Elvor instead of Minae as the immediately preceding holder.

### pt20: neither_correct

Which did I buy first, my blue jug or my brass bell?

Evidence: ["You bought the blue jug in February 2026.", "You own a brass bell, but its purchase date is not recorded."]

**qwen3:0.6b — incorrect**

blue jug

Chooses the blue jug first without the bell purchase date needed to establish order.

**qwen3:1.7b — incorrect**

You bought the blue jug in February 2026. Since the purchase date of the brass bell is not recorded, the blue jug was bought first.

Infers an unsupported purchase order from the missing bell date.

### pt22: neither_correct

Did my visit to Renla finish before the craft delivery arrived?

Evidence: ["Your visit to Renla began at 13:00 on 5 June. Its end time is unrecorded.", "The craft delivery arrived at 14:10 that day."]

**qwen3:0.6b — incorrect**

No

Definitively answers no although the visit end time is unknown.

**qwen3:1.7b — incorrect**

No, your visit to Renla did not finish before the craft delivery arrived.

Claims the visit did not finish first despite its unrecorded end time.

### pt24: neither_correct

Which of my two recorded craft visits lasted longer?

Evidence: ["Your first craft visit lasted 70 minutes.", "Your second craft visit began at 10:30, but its ending time and duration were not recorded."]

**qwen3:0.6b — partial**

The first craft visit lasted 70 minutes.

Accurately gives the first duration but does not say the visits cannot be compared without the second duration.

**qwen3:1.7b — incorrect**

Your first craft visit lasted longer.

Claims the first visit was longer despite the unknown second duration.

### pt25: neither_correct

How many days passed before I returned the borrowed art book?

Evidence: ["You borrowed the art book on 2 May 2026.", "Current confirmed note A: you returned it on 7 May 2026.", "Equally authoritative note B: you returned the same book on 9 May 2026. Neither note corrects the other."]

**qwen3:0.6b — incorrect**

2 days

Invents two elapsed days and omits the unresolved return dates with five- and seven-day possibilities.

**qwen3:1.7b — incorrect**

3 days

Invents three days instead of reporting conflicting returns with conditional five- and seven-day durations.

### pt26: neither_correct

Describe how my drawing-group venue changed and tell me where it meets now.

Evidence: ["Your drawing group originally met in the attic room.", "Current confirmed update A moves it to the east lounge.", "Equally current confirmed update B moves the same group to the courtyard room. Neither update has priority."]

**qwen3:0.6b — incorrect**

The drawing-group venue has changed from the attic room to the east lounge, and it is currently located in the courtyard room.

Turns equally current venue updates into an unsupported sequence and selects the courtyard room as current.

**qwen3:1.7b — incorrect**

Your drawing group's venue has changed twice. Initially, it was in the attic room. Update A moved it to the east lounge, and Update B moved it to the courtyard room. Currently, the group meets in the courtyard room.

Invents two sequential venue changes and a definitive courtyard meeting instead of reporting conflicting current updates.

### pt27: neither_correct

Did my puzzle session finish before or after my call with Wena began?

Evidence: ["Your call with Wena began at 16:00.", "Current log A says your puzzle session ended at 15:50 that day.", "Equally authoritative log B says the same session ended at 16:15. Neither supersedes the other."]

**qwen3:0.6b — incorrect**

before

Chooses before although conflicting session end times support opposite relations to the call.

**qwen3:1.7b — incorrect**

Your puzzle session finished after your call with Wena began.

Selects after despite conflicting end times supporting both before and after.

### pt29: neither_correct

What was my most recently completed sewing project?

Evidence: ["You completed the blue pouch on 10 April 2026.", "Current record A dates completion of the red case to 8 April 2026.", "Equally authoritative record B dates the same red case completion to 12 April 2026. These are the only two completed projects; neither record has priority."]

**qwen3:0.6b — incorrect**

The most recently completed sewing project is the red case on 8 April 2026.

Calls the red case latest at 8 April despite the later blue pouch and unresolved conflicting red-case date.

**qwen3:1.7b — incorrect**

Your most recently completed sewing project was the blue pouch, which was completed on 10 April 2026.

Chooses the blue pouch as latest without resolving the competing red-case completion dates.

### pt30: neither_correct

How much earlier did I move my weekly plant-checking time?

Evidence: ["Your old weekly plant-checking time was 17:00.", "Current confirmed change A moves it to 16:30.", "Equally current confirmed change B moves the same routine to 16:10. Neither change supersedes the other."]

**qwen3:0.6b — incorrect**

16:10

Selects one conflicting new time and gives no conditional thirty- versus fifty-minute shift.

**qwen3:1.7b — incorrect**

You moved your weekly plant-checking time 10 minutes earlier.

Invents a ten-minute shift and omits the unresolved thirty-versus-fifty-minute alternatives.

### rg04: neither_correct

There are seven bowls on a shelf. I put away four more and take two out. How many remain?

Evidence: []

**qwen3:0.6b — incorrect**

3

Gives three bowls instead of nine.

**qwen3:1.7b — incorrect**

There are 7 - 4 + 2 = 5 bowls remaining.

Reverses both bowl operations and gives five instead of nine.

### rg10: neither_correct

Why should a calendar event include a date as well as a time?

Evidence: []

**qwen3:0.6b — partial**

A calendar event includes a date and time to help users plan their activities, track time, and organize events effectively.

Gives generic planning benefits but does not explain that time alone fails to identify the day.

**qwen3:1.7b — partial**

A calendar event should include a date as well as a time to ensure clarity and accuracy. The date specifies when the event occurs, while the time indicates the exact moment. This helps participants understand the timing and schedule properly.

Gives general clarity benefits but does not clearly distinguish which day from the time within that day.

### rg21: neither_correct

What does alphabetical order mean when organising recipe titles?

Evidence: []

**qwen3:0.6b — partial**

Alphabetical order means arranging items in the order of their alphabetical sequence, such as 'apple' before 'banana' in a recipe title list.

Explains initial alphabetical order with an example but omits using later letters when earlier letters tie.

**qwen3:1.7b — partial**

Alphabetical order when organising recipe titles refers to arranging the titles in ascending order based on their first letter of the alphabet. This means the titles are sorted from A to Z, making it easier to locate and reference recipes by their starting letter.

Explains first-letter A-to-Z sorting but omits comparing later letters when first letters tie.

### rg22: neither_correct

Why can opening a window let a cooking smell leave a room?

Evidence: []

**qwen3:0.6b — partial**

Because opening a window allows air to circulate, which can carry cooking smells through the room.

Connects moving air to carrying smells through the room but does not explain exchange carrying smell outside or diluting it.

**qwen3:1.7b — partial**

Opening a window allows a cooking smell to escape a room by creating a pathway for air to circulate, enabling the scent to spread throughout the room.

Links a window to air circulation but describes spreading the scent within the room rather than clearly explaining outward air exchange or dilution.

### rg28: neither_correct

What colour is the fictional Orinvale recycling bin according to these notices?

Evidence: ["Notice A: The Orinvale recycling bin is violet.", "Notice B: The same Orinvale recycling bin is orange. Both notices are current and equally authoritative."]

**qwen3:0.6b — incorrect**

orange

Chooses orange despite equally authoritative conflicting violet and orange notices.

**qwen3:1.7b — partial**

The fictional Orinvale recycling bin is violet according to Notice A.

Accurately attributes violet to Notice A but omits the equally authoritative orange notice and the resulting uncertainty.

### rg29: neither_correct

Where should visitors leave umbrellas at the fictional Marlowe hall?

Evidence: ["Current hall instruction: leave umbrellas in the entry stand.", "Another equally authoritative current instruction: leave umbrellas in the side-room basket. Neither replaces the other."]

**qwen3:0.6b — incorrect**

The entry stand.

Chooses the entry stand despite equally authoritative conflicting umbrella instructions.

**qwen3:1.7b — incorrect**

Visitors should leave umbrellas in the entry stand, as that is the current hall instruction. The side-room basket instruction is not applicable here, as it is not a replacement for the entry stand.

Chooses the entry stand and falsely dismisses the equally authoritative basket instruction.

### rg30: neither_correct

How long is a standard session on the fictional Tern laundry timer?

Evidence: ["Current Tern label: standard session 25 minutes.", "Current Tern leaflet: standard session 35 minutes. Both refer to the same timer and neither has priority."]

**qwen3:0.6b — incorrect**

25 minutes

Chooses twenty-five minutes despite the equally authoritative thirty-five-minute source.

**qwen3:1.7b — incorrect**

A standard session on the fictional Tern laundry timer is 35 minutes.

Chooses thirty-five minutes without reporting the equally current twenty-five-minute label.

### cg04: only_large_correct

Use only bread, cucumber and hummus to suggest a no-cook snack. Give two preparation steps, mention all three ingredients, and do not add an ingredient.

Evidence: []

**qwen3:0.6b — partial**

1. Combine bread, cucumber, and hummus in a bowl. 2. Add a few drops of olive oil to enhance flavor.

Gives two no-cook steps mentioning all three ingredients but adds forbidden olive oil.

**qwen3:1.7b — complete**

1. Spread cucumber slices on a plate and top with hummus. 2. Add a slice of bread to the top of the hummus. All three ingredients are used: cucumber, hummus, and bread.

Provides two no-cook steps using only bread, cucumber, and hummus.

### cg05: only_large_correct

A shelf can hold 12 kilograms. A lamp weighs 3, books weigh 7, and a basket weighs 4 kilograms. Choose exactly two items, include the books, and explain in one sentence why they fit.

Evidence: []

**qwen3:0.6b — partial**

A shelf can hold 12 kilograms, and a basket weighs 4 kilograms. The books weigh 7 kilograms, so two items fit: the books and the basket.

Chooses the valid books-and-basket pair but does not give a one-sentence sum of eleven kilograms against the limit.

**qwen3:1.7b — complete**

The books and the basket can be chosen. The books weigh 7 kg and the basket weighs 4 kg, totaling 11 kg, which is less than the shelf's capacity of 12 kg.

Chooses exactly books and basket and explains in one sentence that 11 kg is within 12 kg.

### cg09: only_large_correct

Suggest two different names for a household robot. Each must be one word, start with B, and contain no more than six letters. Give names only.

Evidence: []

**qwen3:0.6b — partial**

Bumblebee, Bumble

Gives two distinct B names and no explanation, but Bumblebee exceeds six letters.

**qwen3:1.7b — complete**

Bebop, Brio

Gives only two distinct one-word B names, each at most six letters.

### cg10: only_large_correct

A craft budget is 19 tokens. Paper costs 7, glue costs 5 and ribbon costs 4. Buy one of each; state the total and change, with no shopping advice.

Evidence: []

**qwen3:0.6b — incorrect**

Total: 19 tokens. Change: 19 - 7 - 5 - 4 = 5 tokens.

Gives nineteen total and five change instead of sixteen and three, including a false subtraction equation.

**qwen3:1.7b — complete**

The total cost is 7 + 5 + 4 = 16. The change would be 19 - 16 = 3.

Correctly calculates sixteen total and three change without shopping advice.

### cg11: only_large_correct

Explain a calendar to a child in at most 25 words. Use no technical terms and include one example involving a birthday.

Evidence: []

**qwen3:0.6b — partial**

A calendar helps you track dates, like a birthday. It shows you the day, month, and year. For example, a birthday is on January 1st, 2023.

Provides a simple calendar explanation and birthday example but uses twenty-six words, exceeding twenty-five.

**qwen3:1.7b — complete**

A calendar is a tool to track dates. It shows days, weeks, and months. For example, your birthday is on the 15th of March.

Uses twenty-four simple words to explain date tracking and gives an explicitly illustrative birthday example.

### cg14: only_large_correct

Prepare a four-item packing list for a short drawing session in the garden. Include paper and a pencil, include something to sit on, and exclude electronic devices.

Evidence: []

**qwen3:0.6b — partial**

paper, pencil, chair, electronic devices excluded

Includes paper, pencil, and seating and excludes electronics, but supplies only three actual packing items.

**qwen3:1.7b — complete**

The four-item packing list for a short drawing session in the garden is: 1. Drawing paper, 2. Pencil, 3. Cushion or mat to sit on, 4. Eraser.

Gives four suitable items including paper, pencil, seating, and an eraser, without electronics.

### cg16: only_large_correct

A robot can carry at most two books per trip. Move five books using the fewest trips. Give the trip count and number of books on each trip; do not carry more than the limit.

Evidence: []

**qwen3:0.6b — incorrect**

2 5

The unexplained numbers do not provide the required three trips with loads two, two, and one.

**qwen3:1.7b — complete**

The robot can carry at most two books per trip. To move five books using the fewest trips, it will need 3 trips. The first two trips will carry 2 books each, and the third trip will carry 1 book.

Correctly gives the minimum three trips with loads two, two, and one.

### cg19: only_large_correct

Make a 20-minute plan using exactly one reading period and one tidying period. Reading must be twice as long as a 5-minute tidying period, and the remaining time must be a break. State all durations.

Evidence: []

**qwen3:0.6b — incorrect**

20 minutes reading period, 5 minutes tidying period, and 15 minutes break.

Proposes forty minutes total with twenty minutes of reading, violating both the twenty-minute budget and two-to-one reading ratio.

**qwen3:1.7b — complete**

The 20-minute plan is as follows: Reading period is 10 minutes (twice as long as a 5-minute tidying period), tidying period is 5 minutes, and the remaining time (5 minutes) is a break.

Assigns one ten-minute reading period, one five-minute tidying period, and a five-minute break, totaling twenty.

### cg21: only_large_correct

Sort these jars by volume from smallest to largest: red 750 ml, green 250 ml, white 500 ml. Give colours only, separated by commas.

Evidence: []

**qwen3:0.6b — incorrect**

green, red, white

Meets the color-only comma format but puts red before the smaller white jar.

**qwen3:1.7b — complete**

green,white,red

Gives only green, white, red in ascending-volume order, separated by commas.

### cg23: only_large_correct

A square tabletop is 60 cm on each side. A cover must hang 10 cm beyond every edge. Give the required square cover size and explain the added length briefly.

Evidence: []

**qwen3:0.6b — incorrect**

The required square cover size is 60 cm on each side. The added length is 10 cm beyond each edge, making the total cover size 60 cm × 60 cm. The added length is 10 cm per side, totaling 20 cm.

Gives a 60-by-60 cover, which provides no overhang; the required size is 80 by 80.

**qwen3:1.7b — complete**

The required square cover size is 80 cm on each side. The added length of 10 cm is added to each edge of the tabletop to ensure the cover hangs beyond every edge.

Correctly gives eighty centimetres on each square side and ten centimetres beyond every edge.

### cg24: only_large_correct

Make a two-sentence reminder to bring a library card on Friday. The first sentence must state the reminder; the second must suggest putting the card beside the door. Do not invent a time.

Evidence: []

**qwen3:0.6b — incorrect**

Make a two-sentence reminder to bring a library card on Friday. The first sentence must state the reminder; the second must suggest putting the card beside the door.

Produces two sentences without an invented time, but repeats instructions for writing a reminder rather than giving the reminder and placement suggestion. The requested central writing task is not performed, so incidental format compliance does not warrant partial credit.

**qwen3:1.7b — complete**

Please bring your library card on Friday. Put the card beside the door.

Uses two sentences with the Friday reminder first and card-beside-door suggestion second, with no invented time.

### cg26: only_large_correct

Choose a visitor slot of at least 45 minutes ending by noon, and provide its exact start and end. If this cannot be established, explain what is missing without proposing an invented slot.

Evidence: ["The fictional Solva visitor room opens sometime in the morning and closes at noon; no exact opening time is supplied."]

**qwen3:0.6b — partial**

No exact opening time is provided.

Identifies the missing opening time but does not explicitly say no guaranteed qualifying forty-five-minute slot can be established.

**qwen3:1.7b — appropriate_abstention**

The visitor room opens in the morning and closes at noon, but the exact opening time is not specified. Therefore, it is not possible to choose a visitor slot of at least 45 minutes ending by noon. The missing information is the exact opening time of the visitor room.

Explains that the unspecified opening time prevents establishing a qualifying visitor slot.

### cg27: only_large_correct

Calculate the total cost for two identical storage baskets plus delivery. State any known subtotal and identify the missing amount; do not assume free delivery.

Evidence: ["Each basket costs 9 tokens. Delivery is charged, but the charge is not listed."]

**qwen3:0.6b — incorrect**

Total cost: $9 * 2 + $9 = $27. Missing amount: $9

Invents a nine-unit delivery charge and a 27-unit total, and changes tokens to dollars.

**qwen3:1.7b — appropriate_abstention**

The subtotal for the storage baskets is 2 * 9 = 18 tokens. The delivery charge is not listed, so it cannot be determined. The total cost is 18 tokens plus the unknown delivery charge.

Correctly supplies the 18-token subtotal and leaves the delivered total unknown because delivery is missing.

### cg29: only_large_correct

Work out how many tiles are in three unopened packs. Give a definite total only if the number of tiles per pack is settled; otherwise give both possible totals with their assumptions.

Evidence: ["Current packaging says 6 tiles per pack. The equally authoritative current product sheet for the same packs says 8; neither source supersedes the other."]

**qwen3:0.6b — incorrect**

6 tiles per pack. The total number of tiles in three unopened packs is 18.

Selects six tiles per pack and eighteen total despite the equally authoritative eight-tile alternative.

**qwen3:1.7b — appropriate_uncertainty**

If the number of tiles per pack is settled as 6, then three unopened packs contain 18 tiles. If the number of tiles per pack is uncertain (with conflicting sources stating 6 and 8), then the total could be either 18 or 24, depending on the actual number of tiles per pack.

Identifies conflicting six- and eight-tile counts and gives eighteen or twenty-four conditionally without an unconditional total.

### cg30: only_large_correct

Summarise the fictional Oriel garden rule in at most two sentences. Include the agreed opening day and the unresolved pet rule; do not settle the disagreement.

Evidence: ["Current sign: open Tuesday; pets allowed.", "Equally authoritative current leaflet: open Tuesday; pets prohibited. Neither replaces the other."]

**qwen3:0.6b — partial**

The Oriel garden rule states that both the current sign (open Tuesday) and the leaflet (open Tuesday) agree on the pet rule, but there is an unresolved conflict between the two rules.

Gives Tuesday and mentions unresolved conflict, but falsely says the sources agree on pets and omits the allowed/prohibited alternatives.

**qwen3:1.7b — appropriate_uncertainty**

The Oriel garden opens every Tuesday, and pets are allowed in accordance with the current sign, but the equally authoritative leaflet prohibits pets, leaving the issue unresolved.

In one sentence gives Tuesday opening and attributes the conflicting pet rules while explicitly leaving them unresolved.

### pr01: only_large_correct

What pattern is on my preferred reading cushion?

Evidence: ["You chose a cushion with tiny sailboats for reading.", "Your outdoor seat pad has yellow checks."]

**qwen3:0.6b — incorrect**

factual

The word factual does not answer the cushion-pattern question.

**qwen3:1.7b — complete**

The pattern on your preferred reading cushion is tiny sailboats.

Correctly identifies tiny sailboats on the reading cushion.

### pr05: only_large_correct

How do I like the curtains arranged while I draw?

Evidence: ["When drawing, you prefer the left curtain open and the right curtain closed."]

**qwen3:0.6b — inappropriate_abstention**

The evidence shows that when drawing, the left curtain should be open and the right closed. However, the question is about how you like the curtains arranged while drawing, which is not addressed in the evidence.

Recites the correct curtain positions but then falsely says the evidence does not address the explicitly recorded preference.

**qwen3:1.7b — complete**

While drawing, you prefer the left curtain to be open and the right curtain to be closed.

Correctly gives left curtain open and right curtain closed.

### pr14: only_large_correct

Which of my nephews collects toy windmills?

Evidence: ["Your nephew Iven collects toy windmills.", "Your nephew Rulan collects postcards."]

**qwen3:0.6b — incorrect**

Rulan

Names postcard collector Rulan instead of windmill collector Iven.

**qwen3:1.7b — complete**

Your nephew Iven collects toy windmills.

Correctly identifies Iven as the nephew collecting toy windmills.

### pr19: only_large_correct

What colour backpack did I choose for the museum visit?

Evidence: ["You chose a lightweight backpack for the museum visit.", "No backpack colour is recorded."]

**qwen3:0.6b — partial**

lightweight backpack

Supplies the known backpack type but does not acknowledge that its color is unknown.

**qwen3:1.7b — appropriate_abstention**

The colour of the backpack cannot be determined from the provided evidence.

Correctly says the backpack color cannot be determined.

### pr21: only_large_correct

How many spare pillowcases did I put in the guest drawer?

Evidence: ["You put spare pillowcases in the guest drawer.", "Their number was not recorded."]

**qwen3:0.6b — incorrect**

0

Invents a zero pillowcase count despite an unrecorded quantity.

**qwen3:1.7b — appropriate_abstention**

The number of spare pillowcases cannot be determined from the provided evidence.

Correctly states that the pillowcase count cannot be determined.

### pt03: only_large_correct

Put my three craft projects in completion order, earliest first, and say which was last.

Evidence: ["You completed the paper mobile on 18 May 2026.", "You completed the felt coaster on 6 May 2026.", "You completed the bead tray on 12 May 2026."]

**qwen3:0.6b — incorrect**

1. Completed the paper mobile on 18 May 2026. 2. Completed the felt coaster on 6 May 2026. 3. Completed the bead tray on 12 May 2026.

Lists the paper mobile before earlier completions and does not identify it as last.

**qwen3:1.7b — complete**

The three craft projects in completion order, from earliest to latest, are: 1. The felt coaster (6 May 2026), 2. The bead tray (12 May 2026), and 3. The paper mobile (18 May 2026).

Correctly orders felt coaster, bead tray, and paper mobile from earliest to latest, establishing the mobile as last.

### pt04: only_large_correct

At 15:00 on 9 April, where was my sketchbook, and where was it by the end of that day?

Evidence: ["On 9 April at 09:00 you put your sketchbook in the desk drawer.", "At 17:00 that day you moved the sketchbook from the drawer to your green tote, where it stayed for the rest of the day."]

**qwen3:0.6b — partial**

green tote

Provides the end-of-day green tote location but omits the desk drawer at 15:00.

**qwen3:1.7b — complete**

At 15:00 on 9 April, your sketchbook was in the desk drawer. By the end of the day, it was in your green tote.

Correctly distinguishes the desk drawer at 15:00 from the green tote at day’s end.

### pt15: only_large_correct

How many more seed packets did I sort in the later session than in the earlier one?

Evidence: ["On 7 March you sorted 8 seed packets.", "On 14 March you sorted 13 seed packets."]

**qwen3:0.6b — incorrect**

6

Says six more packets; the supported difference is five.

**qwen3:1.7b — complete**

You sorted 13 seed packets in the later session and 8 in the earlier session. The difference is 13 - 8 = 5.

Correctly calculates five more packets in the later session.

### pt18: only_large_correct

Give a short account of my borrowed lantern: who lent it, when I returned it, and whether I still have it.

Evidence: ["On 15 October 2025 your neighbour Vasko lent you a lantern.", "You returned that lantern to Vasko on 19 October 2025.", "You have not borrowed it again."]

**qwen3:0.6b — partial**

Vasko lent you a lantern on 15 October 2025, returned it on 19 October 2025, and you still have it.

Correctly names the lender and return date but misattributes the return and falsely says the user still has the lantern.

**qwen3:1.7b — complete**

The lantern was lent by your neighbour Vasko on 15 October 2025. You returned it to Vasko on 19 October 2025. You no longer have the lantern.

Correctly supplies neighbour Vasko, return on 19 October 2025, and no continued possession.

### pt21: only_large_correct

What was my sketching routine before I switched to the current one?

Evidence: ["Your current sketching routine is Sunday mornings on the patio.", "You said this replaced an earlier routine, but its day, time and place were not recorded."]

**qwen3:0.6b — incorrect**

The sketching routine before switching was on Sunday mornings on the patio.

Misstates the current Sunday patio routine as the unrecorded earlier routine.

**qwen3:1.7b — appropriate_abstention**

Your previous sketching routine was not recorded in the evidence provided.

Correctly says the previous routine was unrecorded and does not substitute the current routine.

### pt23: only_large_correct

Where is my travel chess set now, after I took it out of the cupboard?

Evidence: ["On 8 August you stored the travel chess set in the study cupboard.", "On 10 August you took it out, but its destination and any later location were not recorded."]

**qwen3:0.6b — incorrect**

The travel chess set is still in the study cupboard, as its destination and later location were not recorded.

Claims the chess set remains in the cupboard despite its recorded removal.

**qwen3:1.7b — appropriate_abstention**

The travel chess set was taken out of the study cupboard on 10 August, but its destination and later location were not recorded. Therefore, its current location is unknown.

Correctly says the current location is unknown after the recorded removal.

### rg03: only_large_correct

What is the practical difference between sorting laundry and folding laundry?

Evidence: []

**qwen3:0.6b — partial**

The practical difference is that sorting laundry involves organizing items in a specific order to maximize efficiency, while folding laundry involves folding individual items to make them compact and easier to carry or store.

Correctly explains compact folding but describes sorting as ordering rather than separating laundry into groups.

**qwen3:1.7b — complete**

Sorting laundry involves organizing clothes by type, color, or category, while folding laundry involves laying out and folding clothes to prepare them for storage or washing. The practical difference lies in the preparation steps: sorting categorizes the laundry, and folding prepares it for future use.

Distinguishes grouping clothes from folding individual clothes for storage.

### rg07: only_large_correct

If a book is due back in five days, does that mean it must be returned exactly five days from now?

Evidence: []

**qwen3:0.6b — incorrect**

Yes, if a book is due back in five days, it must be returned exactly five days from now.

Incorrectly treats a return deadline as prohibiting an earlier return.

**qwen3:1.7b — complete**

No, it does not necessarily mean that the book must be returned exactly five days from now. The due date is a specific point in time, but the actual return date may be adjusted based on circumstances such as the library's policies, availability of the book, or other factors. The five-day period refers to the time frame within which the book must be returned, not the exact date.

Explains that five days defines the return deadline and a permissible timeframe rather than one mandatory exact return instant.

### rg09: only_large_correct

A watering jug holds two litres. How much water do three full jugs hold?

Evidence: []

**qwen3:0.6b — incorrect**

9

Gives nine instead of six litres.

**qwen3:1.7b — complete**

Six litres

Correctly gives six litres.

### rg15: only_large_correct

A drawer is 40 centimetres wide and a tray is 45 centimetres wide. Can the tray fit flat across that width without bending?

Evidence: []

**qwen3:0.6b — partial**

No, the tray cannot fit flat across the drawer's width without bending.

Correctly says the tray cannot fit, but does not give the required width difference or comparison.

**qwen3:1.7b — complete**

The tray cannot fit flat across the width of the drawer without bending, as the tray is 45 centimetres wide, which is slightly wider than the drawer's 40 centimetres. Therefore, it would need to be bent to fit.

Correctly rejects a flat fit across the stated width and compares 45 cm with 40 cm, establishing the five-centimetre excess. The question does not require separately spelling out the subtraction, and no diagonal fit is assumed.

### rg17: only_large_correct

A robot heard an unclear room name in a cleaning request. What should it do before choosing a room?

Evidence: []

**qwen3:0.6b — incorrect**

The robot should analyze the room name to determine its location before choosing a room.

Recommends analyzing the unclear name but never requests clarification or confirmation.

**qwen3:1.7b — complete**

The robot should first confirm the room name by asking the user to clarify or provide the exact name of the room.

Correctly recommends asking the user to clarify or confirm the room name before choosing.

### rg18: only_large_correct

Why might a transparent storage jar help when checking whether rice is running low?

Evidence: []

**qwen3:0.6b — partial**

A transparent storage jar might help check rice running low by allowing easy observation of the rice's state, including moisture levels and any signs of spoilage.

Mentions visual observation through the jar but discusses condition and spoilage instead of seeing how much rice remains.

**qwen3:1.7b — complete**

A transparent storage jar allows for easy visual inspection of the rice, making it easier to determine if it is running low.

Explains that transparency permits seeing the remaining rice and noticing a low supply.

### rg19: only_large_correct

What is a backup copy of a shopping list useful for?

Evidence: []

**qwen3:0.6b — partial**

to store or protect information

Gives a generic information-protection purpose but does not explain using the backup if the original list is lost or unavailable.

**qwen3:1.7b — complete**

A backup copy of a shopping list is useful for preserving the list in case of data loss, device failure, or accidental deletion.

Explains that a backup preserves the shopping list when the original data or device becomes unavailable.

### rg24: only_large_correct

A clock reads 10:20. What time will it show 35 minutes later?

Evidence: []

**qwen3:0.6b — incorrect**

10:20 + 35 minutes = 11:55

Falsely adds thirty-five minutes to 10:20 as 11:55 instead of 10:55.

**qwen3:1.7b — complete**

The clock will show 10:55.

Correctly adds thirty-five minutes to get 10:55.

### rg25: only_large_correct

At what time does the fictional Elm Quay craft room close on Sunday?

Evidence: ["Elm Quay craft room opens at 10:00 on Sunday. Its closing time is not listed."]

**qwen3:0.6b — incorrect**

10:00

Uses the opening time as an unsupported closing time.

**qwen3:1.7b — appropriate_abstention**

The closing time of the fictional Elm Quay craft room on Sunday is not listed.

Correctly states that Sunday closing time is unlisted.

### rg26: only_large_correct

How many plates fit in the fictional Pavo dish rack?

Evidence: ["The Pavo rack has a removable cutlery cup. No plate capacity is recorded."]

**qwen3:0.6b — incorrect**

0

Invents zero as the plate capacity when no capacity is recorded.

**qwen3:1.7b — appropriate_abstention**

The Pavo dish rack has a removable cutlery cup but no plate capacity is recorded. Therefore, the number of plates that fit in the Pavo dish rack cannot be determined from the provided evidence.

Correctly states the unrecorded plate capacity prevents determining a number.

### rg27: only_large_correct

Does the fictional Vireo reading room allow visitors to bring snacks?

Evidence: ["The Vireo reading room asks visitors to silence phones. Its food policy is unspecified."]

**qwen3:0.6b — incorrect**

No, the fictional Vireo reading room does not allow visitors to bring snacks.

Invents a snack ban from evidence with no food policy.

**qwen3:1.7b — appropriate_abstention**

The Vireo reading room's food policy is unspecified, so it is not possible to determine if visitors are allowed to bring snacks.

Correctly leaves the snack policy unknown because the food policy is unspecified.

### cg17: only_small_correct

Write a label for a box of spare buttons. It must contain "buttons", have at most four words, and contain no punctuation.

Evidence: []

**qwen3:0.6b — complete**

buttons

The single-word label contains buttons and has no punctuation.

**qwen3:1.7b — partial**

A box of spare buttons

Includes buttons and has no punctuation, but the five-word label exceeds four words.

### cg20: only_small_correct

Rewrite "You left the hallway a mess again" as one polite request. Mention the hallway, avoid blame, and use no more than 15 words.

Evidence: []

**qwen3:0.6b — complete**

Please clean up the hallway.

Gives a six-word polite hallway request with no blame.

**qwen3:1.7b — partial**

Please clean the hallway again to avoid leaving it a mess.

Makes a short polite hallway request but retains blame through again and avoiding leaving it a mess.

### pt17: only_small_correct

By 16:00, which of my planned jobs were completed and which had not started?

Evidence: ["Your shelf sorting ran 14:00-14:25.", "Your card writing ran 15:10-15:40.", "Your button sorting was scheduled to start at 16:20 and did start then. All are on 21 May."]

**qwen3:0.6b — complete**

Your shelf sorting was completed at 14:00-14:25, and your card writing was completed at 15:10-15:40. Your button sorting started at 16:20 and is on 21 May.

Identifies the first two jobs as completed and gives the button task start of 16:20, establishing that it had not begun by 16:00.

**qwen3:1.7b — partial**

By 16:00, your shelf sorting and card writing were completed, as they were scheduled to run before 16:25 and 15:40 respectively. Your button sorting had already started at 16:20 and was in progress by 16:00.

Correctly marks shelf sorting and card writing complete but falsely says the 16:20 button task was already in progress at 16:00.

### rg11: only_small_correct

What is one simple way to stop loose socks getting separated during washing?

Evidence: []

**qwen3:0.6b — complete**

Use a tight, straight washing bag or a tight, straight cloth to prevent loose socks from separating.

A washing bag is a plausible simple way to keep socks together despite awkward wording.

**qwen3:1.7b — partial**

One simple way to stop loose socks getting separated during washing is to use a sock separator or a laundry basket with small holes to keep the socks from slipping apart.

A sock separator is plausibly a device for keeping socks organized during washing, so the proposed method has partial merit without requiring the reference mesh bag. The alternative claim that a small-holed laundry basket keeps socks together during washing lacks a credible securing mechanism and is unsupported.
