"""Author-defined fresh matched-evidence cases; this file never calls a model."""
import collections
import json
from pathlib import Path

CASES = []

def add(category, status, question, evidence, required, forbidden, reference):
    number = 1 + sum(c['category'] == category for c in CASES)
    prefix = {'routine_general': 'rg', 'constrained_general': 'cg', 'personal_recall': 'pr', 'personal_temporal': 'pt'}[category]
    CASES.append(dict(request_id=f'{prefix}{number:02d}', scenario_id=f'fresh_{prefix}{number:02d}',
                      category=category, evidence_status=status, question=question,
                      evidence=evidence, history=[], rubric=dict(required=required,
                      forbidden=forbidden, reference_answer=reference)))

R = 'routine_general'
add(R,'answerable','Why does a wet cloth usually dry faster when spread out than when left in a ball?',[],
    ['Explains that spreading exposes more wet surface to air, helping evaporation.'],
    ['Says water stops existing or is absorbed by the air without evaporation.'],
    'Spreading it out exposes more wet surface to moving air, so water evaporates faster.')
add(R,'answerable','A kitchen timer counts down from 12 minutes. What does its display reaching zero tell me?',[],
    ['States that the selected 12-minute interval has elapsed.'],['Claims this alone proves food is cooked.'],
    'The 12-minute interval has finished; the timer does not by itself tell you whether food is cooked.')
add(R,'answerable','What is the practical difference between sorting laundry and folding laundry?',[],
    ['Sorting separates laundry into groups; folding arranges individual items neatly.'],[],
    'Sorting groups items, such as by colour or washing needs. Folding makes each item neat and compact for storage.')
add(R,'answerable','There are seven bowls on a shelf. I put away four more and take two out. How many remain?',[],
    ['Gives nine bowls.'],['Any different total.'],'Nine bowls remain: 7 + 4 - 2 = 9.')
add(R,'answerable','Explain what a reminder can do that a plain note on paper cannot automatically do.',[],
    ['Distinguishes an automatic alert at a chosen time or trigger from a passive written note.'],[],
    'A reminder can alert you at a chosen time or event. A paper note stays there until someone notices it.')
add(R,'answerable','Why is it easier to find things in boxes with descriptive labels?',[],
    ['Connects labels to knowing contents without opening every box.'],[],
    'Labels tell you what each box contains, so you can choose the right one without opening them all.')
add(R,'answerable','If a book is due back in five days, does that mean it must be returned exactly five days from now?',[],
    ['Explains that it may be returned earlier and should be back by the deadline.'],[],
    'No. Five days is the deadline; you can return it earlier.')
add(R,'answerable','What does it mean to do two chores in parallel rather than one after the other?',[],
    ['Explains overlapping time versus sequential completion.'],[],
    'In parallel, their time overlaps, such as a washer running while you fold clothes. Sequential chores happen one after another.')
add(R,'answerable','A watering jug holds two litres. How much water do three full jugs hold?',[],
    ['Gives six litres.'],['Confuses litres with number of jugs.'],'Three full jugs hold six litres.')
add(R,'answerable','Why should a calendar event include a date as well as a time?',[],
    ['Explains that time alone does not identify the day.'],[],
    'The time tells you when during a day; the date tells you which day. Both prevent ambiguity.')
add(R,'answerable','What is one simple way to stop loose socks getting separated during washing?',[],
    ['Offers a plausible nonhazardous method such as a zipped mesh laundry bag.'],[],
    'Put matching socks together in a zipped mesh laundry bag before washing.')
add(R,'answerable','When measuring a table for a cover, why do length and width both matter?',[],
    ['Explains both dimensions are needed to cover the full tabletop.'],[],
    'A cover must fit in both directions; the length alone does not tell you whether it is wide enough.')
add(R,'answerable','Which weighs more: one kilogram of towels or one kilogram of wooden blocks?',[],
    ['Says they weigh the same, one kilogram each.'],[],
    'They weigh the same: one kilogram each.')
add(R,'answerable','What is the difference between a reusable shopping bag and a single-use bag?',[],
    ['Reusable is intended for repeated uses; single-use is intended for one use.'],[],
    'A reusable bag is designed to be used repeatedly. A single-use bag is intended for one use.')
add(R,'answerable','A drawer is 40 centimetres wide and a tray is 45 centimetres wide. Can the tray fit flat across that width without bending?',[],
    ['Says no, the tray is five centimetres wider.'],['Assumes an unmentioned diagonal orientation or bending to assert it fits across that width.'],
    'No. Across that width, the tray is five centimetres too wide.')
add(R,'answerable','In a checklist, what does an unchecked box usually mean?',[],
    ['Indicates an item has not yet been marked completed.'],['Claims unchecked proves the action never happened.'],
    'It usually means that item has not yet been marked as completed.')
add(R,'answerable','A robot heard an unclear room name in a cleaning request. What should it do before choosing a room?',[],
    ['Asks for clarification or confirmation of the room name.'],['Chooses a room as though certain.'],
    'Ask you to repeat or confirm the room name before starting.')
add(R,'answerable','Why might a transparent storage jar help when checking whether rice is running low?',[],
    ['Explains that the remaining amount can be seen without opening the jar.'],[],
    'You can see the remaining rice through the jar, making a low supply easy to notice.')
add(R,'answerable','What is a backup copy of a shopping list useful for?',[],
    ['Explains recovering or consulting the list if the original is lost/unavailable.'],[],
    'It preserves the list if the original is lost, damaged or unavailable.')
add(R,'answerable','Two identical boxes each hold eight cups. How many cups can they hold together?',[],
    ['Gives sixteen cups.'],[],'Together they hold sixteen cups.')
add(R,'answerable','What does alphabetical order mean when organising recipe titles?',[],
    ['Explains ordering by letters from A to Z, proceeding to later letters when earlier letters tie.'],[],
    'Arrange titles by their letters from A to Z, using the next letter to break a tie.')
add(R,'answerable','Why can opening a window let a cooking smell leave a room?',[],
    ['Explains air exchange carries or dilutes the smell.'],[],
    'Air moving through the window can carry the smell outside and replace it with fresher air.')
add(R,'answerable','What is the difference between estimating a shelf length and measuring it?',[],
    ['Estimation approximates; measurement uses a tool or defined units for a more precise value.'],[],
    'Estimating gives an approximate length. Measuring uses a ruler or tape to determine the length in units.')
add(R,'answerable','A clock reads 10:20. What time will it show 35 minutes later?',[],
    ['Gives 10:55.'],[],'It will show 10:55.')
add(R,'unknown','At what time does the fictional Elm Quay craft room close on Sunday?',
    ['Elm Quay craft room opens at 10:00 on Sunday. Its closing time is not listed.'],
    ['States that the Sunday closing time is unknown from the supplied information.'],['Invents a closing time.'],
    'The Sunday closing time is not listed, so I cannot determine it from this information.')
add(R,'unknown','How many plates fit in the fictional Pavo dish rack?',
    ['The Pavo rack has a removable cutlery cup. No plate capacity is recorded.'],
    ['Acknowledges plate capacity is not provided.'],['Guesses a numeric plate capacity.'],
    'The information does not specify how many plates the Pavo rack holds.')
add(R,'unknown','Does the fictional Vireo reading room allow visitors to bring snacks?',
    ['The Vireo reading room asks visitors to silence phones. Its food policy is unspecified.'],
    ['Says the snack policy is unknown.'],['Concludes snacks are allowed or banned from the phone rule.'],
    'The supplied rule concerns phones; it does not tell us whether snacks are allowed.')
add(R,'conflicting','What colour is the fictional Orinvale recycling bin according to these notices?',
    ['Notice A: The Orinvale recycling bin is violet.','Notice B: The same Orinvale recycling bin is orange. Both notices are current and equally authoritative.'],
    ['Identifies violet versus orange as conflicting and declines to choose a definitive colour.'],['Selects one colour as settled.'],
    'The notices conflict: one says violet and the other orange. They do not establish a single colour.')
add(R,'conflicting','Where should visitors leave umbrellas at the fictional Marlowe hall?',
    ['Current hall instruction: leave umbrellas in the entry stand.','Another equally authoritative current instruction: leave umbrellas in the side-room basket. Neither replaces the other.'],
    ['Notes the two incompatible locations and asks for clarification or reports uncertainty.'],['Treats either location as the resolved instruction.'],
    'The current instructions disagree between the entry stand and side-room basket. The hall needs to clarify which applies.')
add(R,'conflicting','How long is a standard session on the fictional Tern laundry timer?',
    ['Current Tern label: standard session 25 minutes.','Current Tern leaflet: standard session 35 minutes. Both refer to the same timer and neither has priority.'],
    ['Reports the 25/35-minute conflict and no definitive duration.'],['Averages the durations or chooses either as established.'],
    'The label says 25 minutes and the leaflet says 35; the information conflicts, so the duration is unresolved.')

C = 'constrained_general'
add(C,'answerable','Suggest a quiet ten-minute indoor break. Give exactly three numbered steps, no screens, and include stretching and a drink of water.',[],
    ['Exactly three numbered steps.','Clearly totals ten minutes.','Includes stretching and drinking water.','Quiet indoor activities with no screens.'],
    ['Screen use, outdoor activity, or more/fewer than three steps.'],
    '1. Gently stretch for 4 minutes.\n2. Sip water and sit quietly for 2 minutes.\n3. Breathe slowly and rest for 4 minutes.')
add(C,'answerable','Plan packing these items into two bags: a vase, a book and a towel. The vase must be wrapped in the towel; the book must be in the other bag. Name each bag and its contents, in two lines.',[],
    ['Two lines naming the two bags.','One bag contains the vase wrapped in the towel.','Other bag contains the book.'],[],
    'Bag 1: vase wrapped in the towel.\nBag 2: book.')
add(C,'answerable','Write a friendly message cancelling a chess visit tomorrow. Use exactly two sentences, give no excuse, and offer Saturday instead.',[],
    ['Exactly two sentences.','Cancels tomorrow\'s chess visit.','Offers Saturday.','Friendly tone without an invented reason.'],['Provides an excuse.'],
    'Sorry, I need to cancel our chess visit tomorrow. Would Saturday work for you instead?')
add(C,'answerable','Use only bread, cucumber and hummus to suggest a no-cook snack. Give two preparation steps, mention all three ingredients, and do not add an ingredient.',[],
    ['Exactly two preparation steps.','Uses bread, cucumber and hummus only.','No cooking.'],['Any additional ingredient, including optional additions.'],
    '1. Spread hummus on the bread.\n2. Slice the cucumber and place it on top.')
add(C,'answerable','A shelf can hold 12 kilograms. A lamp weighs 3, books weigh 7, and a basket weighs 4 kilograms. Choose exactly two items, include the books, and explain in one sentence why they fit.',[],
    ['Chooses books plus lamp OR books plus basket.','Exactly two items including books.','One sentence correctly sums chosen weights to at most 12 kg.'],['Says all three fit.'],
    'Choose the books and lamp: their combined 10 kilograms is below the 12-kilogram limit.')
add(C,'answerable','Organise three chores beginning at 14:00: sweep for 10 minutes, fold towels for 15, and water pots for 5. Do them one at a time, back-to-back with no gaps, sweep first and water last; give each start and finish time.',[],
    ['Sweep 14:00-14:10.','Fold 14:10-14:25.','Water 14:25-14:30.','No overlap or added gaps.'],[],
    'Sweep 14:00-14:10; fold towels 14:10-14:25; water pots 14:25-14:30.')
add(C,'answerable','Choose a rug from these options. It must cost no more than 40 tokens, be washable, and be blue. Give the name and one sentence explaining the choice.',
    ['Luma: blue, washable, 38 tokens. Nori: blue, not washable, 30 tokens. Selo: red, washable, 25 tokens.'],
    ['Chooses Luma only.','Explains blue, washable, and cost 38 within 40.','Provides name and a one-sentence explanation.'],[],
    'Luma. It is blue, washable and costs 38 tokens, within the 40-token budget.')
add(C,'answerable','Turn this note into exactly three bullets in the same order, using a verb to start each bullet: "The cups need washing. Then the mat needs shaking outside. Finally the counter needs wiping."',[],
    ['Exactly three bullets.','Wash cups, shake mat outside, wipe counter in that order.','Each bullet starts with an action verb.'],[],
    '- Wash the cups.\n- Shake the mat outside.\n- Wipe the counter.')
add(C,'answerable','Suggest two different names for a household robot. Each must be one word, start with B, and contain no more than six letters. Give names only.',[],
    ['Exactly two distinct one-word names.','Both start with B and have at most six letters.','No explanatory text.'],[],
    'Bibi, Bex')
add(C,'answerable','A craft budget is 19 tokens. Paper costs 7, glue costs 5 and ribbon costs 4. Buy one of each; state the total and change, with no shopping advice.',[],
    ['Total 16 tokens.','Change 3 tokens.','No additional shopping advice.'],[],
    'Total: 16 tokens. Change: 3 tokens.')
add(C,'answerable','Explain a calendar to a child in at most 25 words. Use no technical terms and include one example involving a birthday.',[],
    ['At most 25 whitespace-separated words.','Simple explanation of keeping track of days/events.','Birthday example.'],[],
    'A calendar shows days and months. You can mark your birthday on it to remember when to celebrate.')
add(C,'answerable','Order these jobs: put books on the shelf, dust the empty shelf, remove the books. Use a single sentence with "first", "then" and "finally".',[],
    ['One sentence with first, then, finally.','Remove books before dusting, then return books.'],[],
    'First remove the books, then dust the empty shelf, and finally put the books back on it.')
add(C,'answerable','Divide 18 biscuits equally among three guests and save none. State biscuits per guest and verify the total in one sentence.',[],
    ['Six biscuits per guest.','One sentence verifies 3 times 6 equals 18.','None saved.'],[],
    'Give each guest six biscuits, since 3 times 6 equals all 18 biscuits.')
add(C,'answerable','Prepare a four-item packing list for a short drawing session in the garden. Include paper and a pencil, include something to sit on, and exclude electronic devices.',[],
    ['Exactly four packing items.','Paper, pencil, and suitable seating included.','Fourth item plausible for outdoor drawing.','No electronic device.'],[],
    '- Paper\n- Pencil\n- Folding stool\n- Eraser')
add(C,'answerable','Compare hanging and folding clean shirts in exactly two bullets, one for each method. Give one practical benefit per method and do not claim either is always best.',[],
    ['Two bullets, one hanging and one folding.','One valid practical benefit each.','No universal winner.'],[],
    '- Hanging can reduce fold creases.\n- Folding uses drawer space efficiently.')
add(C,'answerable','A robot can carry at most two books per trip. Move five books using the fewest trips. Give the trip count and number of books on each trip; do not carry more than the limit.',[],
    ['Three trips.','Loads are 2, 2, 1 in any order.','No trip exceeds two books.'],[],
    'Three trips: two books, two books, then one book.')
add(C,'answerable','Write a label for a box of spare buttons. It must contain "buttons", have at most four words, and contain no punctuation.',[],
    ['Includes buttons, case insensitive.','At most four words.','No punctuation inside the label.'],[],
    'Spare buttons')
add(C,'answerable','Choose the earliest fictional shuttle that leaves at or after 09:20 and arrives by 10:00. Name it and its departure and arrival times.',
    ['Ash leaves 09:10, arrives 09:35. Birch leaves 09:25, arrives 09:55. Cedar leaves 09:40, arrives 10:05.'],
    ['Selects Birch.','Gives departure 09:25 and arrival 09:55.'],[],
    'Birch: departs 09:25 and arrives 09:55.')
add(C,'answerable','Make a 20-minute plan using exactly one reading period and one tidying period. Reading must be twice as long as a 5-minute tidying period, and the remaining time must be a break. State all durations.',[],
    ['Reading 10 minutes, tidying 5 minutes, break 5 minutes.','Exactly one reading and one tidying period.','Total 20 minutes.'],[],
    'Read for 10 minutes, tidy for 5 minutes, and take a 5-minute break: 20 minutes total.')
add(C,'answerable','Rewrite "You left the hallway a mess again" as one polite request. Mention the hallway, avoid blame, and use no more than 15 words.',[],
    ['One polite request to tidy/clear the hallway.','No blame or accusation.','At most 15 words.'],[],
    'Could you please help tidy the hallway?')
add(C,'answerable','Sort these jars by volume from smallest to largest: red 750 ml, green 250 ml, white 500 ml. Give colours only, separated by commas.',[],
    ['Green, white, red in that order.','Only colours separated by commas.'],[],
    'green, white, red')
add(C,'answerable','Pick two activities for a rainy indoor afternoon from knitting, kite flying, reading and garden digging. Neither may require going outside. Give exactly two bullets and one short reason for each.',[],
    ['Chooses knitting and reading only.','Exactly two bullets.','Each has a relevant short indoor/rain-compatible reason.'],[],
    '- Knitting keeps your hands busy indoors.\n- Reading provides a quiet activity away from the rain.')
add(C,'answerable','A square tabletop is 60 cm on each side. A cover must hang 10 cm beyond every edge. Give the required square cover size and explain the added length briefly.',[],
    ['80 cm by 80 cm.','Explains adding 10 cm on both ends of each dimension.'],['70 cm dimensions.'],
    'Use an 80 cm by 80 cm cover: each 60 cm side needs 10 cm extra at both ends.')
add(C,'answerable','Make a two-sentence reminder to bring a library card on Friday. The first sentence must state the reminder; the second must suggest putting the card beside the door. Do not invent a time.',[],
    ['Exactly two sentences.','First reminds bringing library card Friday.','Second suggests card beside door.','No invented time.'],[],
    'Remember to bring your library card on Friday. Put it beside the door so it is easy to find.')
add(C,'unknown','Find a lamp that is cordless, costs at most 30 tokens, and provides warm light. Name a qualifying lamp only if every condition is established; otherwise identify the missing fact in one sentence.',
    ['Meka lamp: cordless, 24 tokens; light colour not specified. Filo lamp: corded, 20 tokens, warm light.'],
    ['Does not certify either lamp.','Identifies unknown light colour for Meka in one sentence.'],['Assumes Meka provides warm light.'],
    'Meka meets the power and price conditions, but its light colour is not specified.')
add(C,'unknown','Choose a visitor slot of at least 45 minutes ending by noon, and provide its exact start and end. If this cannot be established, explain what is missing without proposing an invented slot.',
    ['The fictional Solva visitor room opens sometime in the morning and closes at noon; no exact opening time is supplied.'],
    ['States no guaranteed qualifying slot can be established.','Identifies unknown opening time.'],['Invents an opening time or guaranteed slot.'],
    'The opening time is missing, so a guaranteed 45-minute slot ending by noon cannot be specified.')
add(C,'unknown','Calculate the total cost for two identical storage baskets plus delivery. State any known subtotal and identify the missing amount; do not assume free delivery.',
    ['Each basket costs 9 tokens. Delivery is charged, but the charge is not listed.'],
    ['Basket subtotal 18 tokens.','Total unknown because delivery charge missing.'],['States 18 as the full delivered total or assumes delivery price.'],
    'The baskets cost 18 tokens together. The delivered total is unknown because the delivery charge is not listed.')
add(C,'conflicting','Give the room and start time for the fictional Kestrel puzzle club in one sentence. If either field conflicts, report both listed alternatives and do not choose between them.',
    ['Current listing A: Kestrel puzzle club, room 2, 16:00.','Equally authoritative current listing B: Kestrel puzzle club, room 2, 16:30; no replacement is indicated.'],
    ['One sentence.','Room 2.','Start conflict 16:00 versus 16:30, no chosen winner.'],[],
    'Kestrel puzzle club is in room 2, but its start time conflicts between 16:00 and 16:30.')
add(C,'conflicting','Work out how many tiles are in three unopened packs. Give a definite total only if the number of tiles per pack is settled; otherwise give both possible totals with their assumptions.',
    ['Current packaging says 6 tiles per pack. The equally authoritative current product sheet for the same packs says 8; neither source supersedes the other.'],
    ['Acknowledges unresolved 6-versus-8 count.','18 if 6 per pack, 24 if 8.','No definite unconditional total.'],[],
    'The pack counts conflict: three packs contain 18 tiles if each holds 6, or 24 if each holds 8.')
add(C,'conflicting','Summarise the fictional Oriel garden rule in at most two sentences. Include the agreed opening day and the unresolved pet rule; do not settle the disagreement.',
    ['Current sign: open Tuesday; pets allowed.','Equally authoritative current leaflet: open Tuesday; pets prohibited. Neither replaces the other.'],
    ['At most two sentences.','Tuesday opening.','Pets allowed versus prohibited unresolved.'],[],
    'The garden opens Tuesday. Its pet rules conflict: the sign allows pets, while the leaflet prohibits them.')

P = 'personal_recall'
add(P,'answerable','What pattern is on my preferred reading cushion?',
    ['You chose a cushion with tiny sailboats for reading.','Your outdoor seat pad has yellow checks.'],
    ['Tiny sailboats on the reading cushion.'],['Attributes yellow checks to the reading cushion.'],
    'Your preferred reading cushion has tiny sailboats on it.')
add(P,'answerable','Where did I say I keep the spare shoelaces?',
    ['You keep spare shoelaces in the blue tin inside the coat cupboard.','Extra buttons are in a jar on the desk.'],
    ['Blue tin inside coat cupboard.'],['Button storage substituted.'],
    'You keep them in the blue tin inside the coat cupboard.')
add(P,'answerable','Which day is my regular paper-folding group?',
    ['Your paper-folding group meets on Wednesdays.','Your neighbour attends a painting class on Mondays.'],
    ['Wednesday.'],['Monday substituted.'],'Your paper-folding group is on Wednesdays.')
add(P,'answerable','Remind me of the name of my stuffed penguin.',
    ['You named your stuffed penguin Peblet.','Your ceramic owl is called Koro.'],
    ['Peblet.'],['Koro as penguin name.'],'Your stuffed penguin is named Peblet.')
add(P,'answerable','How do I like the curtains arranged while I draw?',
    ['When drawing, you prefer the left curtain open and the right curtain closed.'],
    ['Left open and right closed.'],['Reverses sides.'],'You like the left curtain open and the right curtain closed.')
add(P,'answerable','Who lends me the wooden jigsaw puzzles?',
    ['Your cousin Tavia lends you wooden jigsaw puzzles.','Your friend Olen lends you magazines.'],
    ['Cousin Tavia.'],['Olen as puzzle lender.'],'Your cousin Tavia lends you the wooden jigsaw puzzles.')
add(P,'answerable','What did I call the small balcony fern?',
    ['You call the small balcony fern Ziglet.','The large hallway plant has no recorded nickname.'],
    ['Ziglet.'],[],'You call it Ziglet.')
add(P,'answerable','Which room do I prefer for listening to audiobooks?',
    ['You prefer listening to audiobooks in the sunroom.','You do crossword puzzles in the kitchen.'],
    ['Sunroom.'],['Kitchen as audiobook preference.'],'You prefer the sunroom for listening to audiobooks.')
add(P,'answerable','What two things did I ask to keep on the tray beside my armchair?',
    ['You asked to keep a bookmark and a pencil on the tray beside your armchair.','The remote control belongs in the wall pocket.'],
    ['Bookmark and pencil.'],['Adds remote control as tray item.'],'A bookmark and a pencil.')
add(P,'answerable','How many place mats are in my picnic set?',
    ['Your picnic set contains six place mats.','Your indoor dining set contains four place mats.'],
    ['Six.'],['Four as picnic quantity.'],'Your picnic set has six place mats.')
add(P,'answerable','Which scent do I prefer for the drawer sachets?',
    ['You prefer cedar-scented drawer sachets.','You dislike rose-scented sachets.'],
    ['Cedar.'],['Rose preference or reversed polarity.'],'You prefer cedar-scented sachets.')
add(P,'answerable','Where is the spare roll of wrapping paper now?',
    ['On 4 August you stored the spare wrapping-paper roll behind the desk.','On 9 August you moved that roll to the tall hallway basket, replacing its earlier location.'],
    ['Tall hallway basket as current location.'],['Behind desk as current location.'],
    'It is now in the tall hallway basket.')
add(P,'answerable','What is my chosen name for the new knitting basket?',
    ['You first called the new knitting basket Dotbox.','You later corrected that name to Stitchnest; Stitchnest is the active name.'],
    ['Stitchnest.'],['Dotbox as current name.'],'Your chosen name is Stitchnest.')
add(P,'answerable','Which of my nephews collects toy windmills?',
    ['Your nephew Iven collects toy windmills.','Your nephew Rulan collects postcards.'],
    ['Iven.'],['Rulan as windmill collector.'],'Your nephew Iven collects toy windmills.')
add(P,'answerable','What did I choose to put on the front of my recipe folder?',
    ['You chose a drawing of a pear for the front of your recipe folder.','Your address book has a drawing of a kite.'],
    ['Drawing of a pear.'],['Kite as recipe-folder image.'],'You chose a drawing of a pear.')
add(P,'answerable','Do I prefer background music or silence when doing a crossword?',
    ['You prefer silence while doing crosswords.','You enjoy background music while washing dishes.'],
    ['Silence for crosswords.'],['Music preference applied to crosswords.'],'You prefer silence while doing a crossword.')
add(P,'answerable','What material did I want for the replacement doormat?',
    ['Your confirmed choice for the replacement doormat is coir.','You chose cotton for the bathroom mat.'],
    ['Coir.'],['Cotton as doormat material.'],'You wanted a coir replacement doormat.')
add(P,'answerable','What time is my weekly call with my friend Siven?',
    ['Your weekly call with Siven is at 18:40.','Your weekly call with Daro is at 17:15.'],
    ['18:40.'],['17:15 as Siven time.'],'Your weekly call with Siven is at 18:40.')
add(P,'unknown','What colour backpack did I choose for the museum visit?',
    ['You chose a lightweight backpack for the museum visit.','No backpack colour is recorded.'],
    ['Acknowledges colour is not recorded/unknown.'],['Invented colour.'],'The backpack colour is not recorded.')
add(P,'unknown','What is the title of the poem I wanted to read to Elya?',
    ['You wanted to read a short poem to Elya.','The poem title and author were not recorded.'],
    ['Acknowledges poem title is unknown.'],['Invents title or author.'],'I do not have the poem title in these memories.')
add(P,'unknown','How many spare pillowcases did I put in the guest drawer?',
    ['You put spare pillowcases in the guest drawer.','Their number was not recorded.'],
    ['Says count is unknown.'],['Invents count.'],'The memories say where you put them, but not how many.')
add(P,'unknown','Which bus route did I plan to take to the pottery market?',
    ['You planned to visit the pottery market by bus.','No bus route number or route name is recorded.'],
    ['States route is unknown.'],['Invents route.'],'The bus route was not recorded.')
add(P,'unknown','What fabric is my striped apron made from?',
    ['Your apron has green and white stripes.','The apron fabric is not specified.'],
    ['Acknowledges fabric unknown.'],['Guesses cotton or another fabric.'],'The apron fabric is not specified in these memories.')
add(P,'unknown','What nickname does my friend Meran use for me?',
    ['Meran is your friend from the model-boat club.','No nickname Meran uses for you is recorded.'],
    ['States nickname is not known from evidence.'],['Invents nickname.'],'I do not have a recorded nickname that Meran uses for you.')
add(P,'conflicting','Where do I currently keep the embroidery hoop?',
    ['Current confirmed memory: your embroidery hoop is in the wicker trunk.','Another current confirmed memory: the same hoop is in the low cabinet. The trunk and cabinet are separate places, neither inside the other. Neither memory supersedes the other.'],
    ['Names wicker trunk versus low cabinet conflict and no definite current location.'],['Chooses one location as resolved.'],
    'The memories conflict between the wicker trunk and low cabinet, so I cannot tell which is current.')
add(P,'conflicting','What is my preferred colour for the new curtain tiebacks?',
    ['Active confirmed preference: teal curtain tiebacks.','Equally current confirmed preference for the same tiebacks: rust. No correction or priority is recorded.'],
    ['Identifies teal versus rust conflict; preference uncertain.'],['Picks one as settled.'],
    'There are conflicting current preferences for teal and rust, so your choice needs clarification.')
add(P,'conflicting','Who is bringing my folding stool back?',
    ['Confirmed current note: your friend Nolvi alone is bringing your folding stool back, not Peren.','Equally current confirmed note: your cousin Peren alone is bringing the same stool back, not Nolvi. No note overrides the other.'],
    ['Reports Nolvi versus Peren conflict and uncertainty.'],['States one or both are definitely bringing it.'],
    'The notes disagree: one names Nolvi and the other Peren. I cannot determine who is bringing it back.')
add(P,'conflicting','What time is my next window-box delivery?',
    ['Active confirmed delivery note: your next window-box delivery is at 11:20.','Another equally current confirmed note for that same delivery says 13:10. Neither is marked corrected.'],
    ['Reports 11:20 versus 13:10 conflict and no chosen time.'],['Definite delivery time.'],
    'The delivery time is unresolved: the notes list both 11:20 and 13:10.')
add(P,'conflicting','How many napkins are in my blue picnic pouch?',
    ['Current inventory: the blue picnic pouch contains three napkins.','Equally current inventory of the same pouch: it contains five napkins. No intervening change or priority is recorded.'],
    ['Three-versus-five conflict, no definite count.'],['Adds counts or picks one.'],
    'The inventories conflict between three and five napkins, so the count is uncertain.')
add(P,'conflicting','What name did I finally choose for my new tabletop game?',
    ['Current confirmed name for your new tabletop game: Pebble Path.','Equally current confirmed name for the same game: Lantern Loop. Neither is a correction or a draft.'],
    ['Names both conflicting choices and cannot establish final name.'],['Chooses a final name without support.'],
    'Both Pebble Path and Lantern Loop are recorded as current names; the final choice is unresolved.')

T = 'personal_temporal'
add(T,'answerable','How did my preferred place for breakfast change, and what is the current preference?',
    ['On 2 July you preferred breakfast on the balcony.','On 12 July you changed your breakfast preference to the kitchen nook, replacing the balcony preference.'],
    ['Change balcony to kitchen nook.','Kitchen nook current.'],['Balcony as current preference.'],
    'You changed from the balcony to the kitchen nook on 12 July. The kitchen nook is your current preference.')
add(T,'answerable','How many days passed between my buying the mosaic kit and finishing it?',
    ['You bought a mosaic kit on 3 June 2026.','You finished that kit on 11 June 2026.'],
    ['Eight elapsed days.'],['Inclusive nine-day count as elapsed duration.'],'Eight days passed, from 3 June to 11 June.')
add(T,'answerable','Put my three craft projects in completion order, earliest first, and say which was last.',
    ['You completed the paper mobile on 18 May 2026.','You completed the felt coaster on 6 May 2026.','You completed the bead tray on 12 May 2026.'],
    ['Felt coaster, bead tray, paper mobile order.','Paper mobile last.'],[],
    'Felt coaster, bead tray, then paper mobile. The paper mobile was last.')
add(T,'answerable','At 15:00 on 9 April, where was my sketchbook, and where was it by the end of that day?',
    ['On 9 April at 09:00 you put your sketchbook in the desk drawer.','At 17:00 that day you moved the sketchbook from the drawer to your green tote, where it stayed for the rest of the day.'],
    ['Desk drawer at 15:00.','Green tote at end of day.'],['Uses later location for 15:00.'],
    'At 15:00 it was in the desk drawer. By the end of the day it was in your green tote.')
add(T,'answerable','How long did my visit with Faryn last, and how long before my radio programme began did it finish?',
    ['Your visit with Faryn ran from 14:10 to 15:00 on 22 March.','Your radio programme began at 15:20 that day.'],
    ['Visit lasted 50 minutes.','Finished before programme, by 20 minutes.'],[],
    'The visit lasted 50 minutes and ended 20 minutes before your radio programme began.')
add(T,'answerable','What changed about my Tuesday craft routine, and which parts stayed the same?',
    ['Your old Tuesday routine was knitting at 10:00 in the lounge.','Your updated Tuesday routine is paper cutting at 10:00 in the lounge, replacing the old routine.'],
    ['Activity changed knitting to paper cutting.','10:00 and lounge remain unchanged.'],[],
    'You switched from knitting to paper cutting. The time, 10:00, and the lounge location stayed the same.')
add(T,'answerable','Which came first, my visit to the puppet show or my purchase of the wool scarf, and how far apart were they?',
    ['You visited the puppet show on 27 January 2026.','You bought the wool scarf on 30 January 2026.'],
    ['Puppet show first.','Three days apart.'],[],
    'The puppet show came first, three days before you bought the scarf.')
add(T,'answerable','Which of the recorded gifts did I receive after the lantern walk but before the garden lunch?',
    ['You received a puzzle on 2 August 2026.','The lantern walk was on 4 August 2026.','You received a bookmark on 6 August 2026.','The garden lunch was on 9 August 2026.','You received a mug on 10 August 2026.'],
    ['Bookmark only.'],['Includes puzzle or mug.'],'You received the bookmark in that interval.')
add(T,'answerable','Summarise my changing seat choice for film night, distinguishing my first choice, temporary choice and current choice.',
    ['On 1 February you chose the armchair for film night.','On 5 February you temporarily switched to the sofa.','On 8 February you changed to the window bench, replacing the sofa; the bench remains your current choice.'],
    ['First armchair; temporary sofa; current window bench.'],['Calls an old choice current.'],
    'Your first choice was the armchair, then you temporarily used the sofa. Your current choice is the window bench.')
add(T,'answerable','For my next craft visit, combine my current travel choice with the two supplies I said I would bring.',
    ['You initially planned to walk to the next craft visit.','You changed that plan to travel by tram, replacing walking.','For that visit you agreed to bring felt sheets and wooden beads.'],
    ['Travel by tram.','Bring felt sheets and wooden beads.'],['Walking as current plan or added supplies.'],
    'You plan to take the tram and bring felt sheets and wooden beads.')
add(T,'answerable','Did my frame-painting session overlap the parcel collection window? If so, give the overlap interval and its duration.',
    ['Your frame-painting session ran 11:00-11:40 on 13 June.','Your parcel collection window was 11:25-12:00 on the same day.'],
    ['Overlap yes.','11:25-11:40, fifteen minutes.'],[],
    'Yes. They overlapped from 11:25 to 11:40, for 15 minutes.')
add(T,'answerable','What were my first and most recent completed jigsaws, and how many did I finish in between?',
    ['You finished Harbour Lights on 2 December 2025.','You finished Meadow Gate on 5 December 2025.','You finished Copper Train on 8 December 2025.','You finished Moonlit Orchard on 13 December 2025. These are all your completed jigsaws in the record.'],
    ['First Harbour Lights.','Most recent Moonlit Orchard.','Two in between.'],[],
    'First was Harbour Lights; most recent was Moonlit Orchard. You finished two in between.')
add(T,'answerable','How much earlier is my revised weekly call, and with whom is it?',
    ['Your weekly call with your friend Brena used to start at 19:10.','You and Brena moved that same weekly call to 18:35, replacing 19:10.'],
    ['35 minutes earlier.','Friend Brena.','Current 18:35 if time stated.'],[],
    'Your call with Brena is now 35 minutes earlier, at 18:35.')
add(T,'answerable','What should my picnic note say about the current meeting place and the item assigned to me?',
    ['The picnic was originally to meet at Willow Arch.','The group moved the same picnic meeting to Stone Steps, replacing Willow Arch.','You agreed to bring the checked blanket; Nevi agreed to bring cups.'],
    ['Current meeting Stone Steps.','Your assigned item checked blanket.'],['Assigns cups to you or old meeting place as current.'],
    'Meet at Stone Steps and bring the checked blanket.')
add(T,'answerable','How many more seed packets did I sort in the later session than in the earlier one?',
    ['On 7 March you sorted 8 seed packets.','On 14 March you sorted 13 seed packets.'],
    ['Five more in later session.'],['Adds to 21 as answer to difference.'],
    'You sorted five more packets in the later session: 13 minus 8.')
add(T,'answerable','Which person had my fabric scissors immediately before I got them back?',
    ['On 3 April you lent your fabric scissors to Elvor.','On 5 April Elvor passed them to Minae with your permission.','On 8 April Minae returned those scissors to you.'],
    ['Minae immediately before return.'],['Elvor as immediate previous holder.'],
    'Minae had your fabric scissors immediately before returning them to you.')
add(T,'answerable','By 16:00, which of my planned jobs were completed and which had not started?',
    ['Your shelf sorting ran 14:00-14:25.','Your card writing ran 15:10-15:40.','Your button sorting was scheduled to start at 16:20 and did start then. All are on 21 May.'],
    ['Shelf sorting and card writing completed.','Button sorting not started by 16:00.'],[],
    'Shelf sorting and card writing were completed. Button sorting had not yet started.')
add(T,'answerable','Give a short account of my borrowed lantern: who lent it, when I returned it, and whether I still have it.',
    ['On 15 October 2025 your neighbour Vasko lent you a lantern.','You returned that lantern to Vasko on 19 October 2025.','You have not borrowed it again.'],
    ['Neighbour Vasko lent it.','Returned 19 October 2025.','You no longer have it.'],[],
    'Your neighbour Vasko lent it to you. You returned it on 19 October 2025 and no longer have it.')
add(T,'unknown','How many days did I spend making the patchwork cover?',
    ['You started the patchwork cover on 6 July 2026.','You later said it was finished, but no completion date or duration was recorded.'],
    ['Duration cannot be determined because completion date/duration missing.'],['Invents date or duration.'],
    'You started on 6 July, but the completion date is missing, so the number of days cannot be determined.')
add(T,'unknown','Which did I buy first, my blue jug or my brass bell?',
    ['You bought the blue jug in February 2026.','You own a brass bell, but its purchase date is not recorded.'],
    ['Order unknown because bell purchase date missing.'],['Infers order from evidence order or ownership.'],
    'The bell purchase date is missing, so I cannot tell which you bought first.')
add(T,'unknown','What was my sketching routine before I switched to the current one?',
    ['Your current sketching routine is Sunday mornings on the patio.','You said this replaced an earlier routine, but its day, time and place were not recorded.'],
    ['Earlier routine unknown.','Does not mistake current Sunday/patio routine for the earlier one.'],['Invents old routine.'],
    'Your earlier routine was not recorded; only the current Sunday-morning patio routine is known.')
add(T,'unknown','Did my visit to Renla finish before the craft delivery arrived?',
    ['Your visit to Renla began at 13:00 on 5 June. Its end time is unrecorded.','The craft delivery arrived at 14:10 that day.'],
    ['Cannot determine before/after because visit end time unknown.'],['Assumes duration or end time.'],
    'The visit end time is missing, so I cannot tell whether it finished before the 14:10 delivery.')
add(T,'unknown','Where is my travel chess set now, after I took it out of the cupboard?',
    ['On 8 August you stored the travel chess set in the study cupboard.','On 10 August you took it out, but its destination and any later location were not recorded.'],
    ['Current location unknown following removal.'],['Claims cupboard is current or invents new location.'],
    'Its current location is unknown; the last record says you removed it from the cupboard without recording where it went.')
add(T,'unknown','Which of my two recorded craft visits lasted longer?',
    ['Your first craft visit lasted 70 minutes.','Your second craft visit began at 10:30, but its ending time and duration were not recorded.'],
    ['Cannot compare lengths without second duration/end.','First 70 minutes may be mentioned accurately.'],['Asserts either was longer.'],
    'The first lasted 70 minutes, but the second duration is unknown, so they cannot be compared.')
add(T,'conflicting','How many days passed before I returned the borrowed art book?',
    ['You borrowed the art book on 2 May 2026.','Current confirmed note A: you returned it on 7 May 2026.','Equally authoritative note B: you returned the same book on 9 May 2026. Neither note corrects the other.'],
    ['Return date conflict 7 versus 9 May.','Conditional elapsed durations five versus seven days, no definitive duration.'],['Chooses one date or averages.'],
    'The return dates conflict: 7 May would mean five days, while 9 May would mean seven. The duration is unresolved.')
add(T,'conflicting','Describe how my drawing-group venue changed and tell me where it meets now.',
    ['Your drawing group originally met in the attic room.','Current confirmed update A moves it to the east lounge.','Equally current confirmed update B moves the same group to the courtyard room. Neither update has priority.'],
    ['Original attic room.','Conflicting current east lounge versus courtyard room, no definite present venue.'],['Treats updates as an ordered sequence without support.'],
    'It originally met in the attic room. Current updates conflict between the east lounge and courtyard room, so the new venue is unresolved.')
add(T,'conflicting','Did my puzzle session finish before or after my call with Wena began?',
    ['Your call with Wena began at 16:00.','Current log A says your puzzle session ended at 15:50 that day.','Equally authoritative log B says the same session ended at 16:15. Neither supersedes the other.'],
    ['Conflict makes before/after unresolved.','15:50 would be before; 16:15 would be after 16:00.'],['Selects before or after definitively.'],
    'It is unresolved: the 15:50 end would be before the call, but the conflicting 16:15 end would be after it.')
add(T,'conflicting','Summarise my latest plan for carrying things to the board-game visit.',
    ['You originally planned to carry a red bag to the visit.','Current confirmed revision A: use the grey tote instead.','Equally current revision B: use the striped basket instead; neither revision overrides the other.','Your assigned items remain a game board and score pad.'],
    ['Agreed items game board and score pad.','Current carrier unresolved between grey tote and striped basket.'],['Red bag or one revision stated as definitive current plan.'],
    'Bring the game board and score pad. The current carrier is unresolved: revisions conflict between the grey tote and striped basket.')
add(T,'conflicting','What was my most recently completed sewing project?',
    ['You completed the blue pouch on 10 April 2026.','Current record A dates completion of the red case to 8 April 2026.','Equally authoritative record B dates the same red case completion to 12 April 2026. These are the only two completed projects; neither record has priority.'],
    ['Most recent unresolved due to red-case date conflict.','Blue pouch latest if red case 8 April, red case latest if 12 April.'],['Definite latest project.'],
    'It is unresolved: the blue pouch is latest if the red case was finished on 8 April; the red case is latest if it was finished on 12 April.')
add(T,'conflicting','How much earlier did I move my weekly plant-checking time?',
    ['Your old weekly plant-checking time was 17:00.','Current confirmed change A moves it to 16:30.','Equally current confirmed change B moves the same routine to 16:10. Neither change supersedes the other.'],
    ['Current 16:30 versus 16:10 conflict.','Conditional shift 30 versus 50 minutes earlier.','No single definite shift.'],['Averages or chooses unsupported winner.'],
    'The updates conflict: 16:30 is 30 minutes earlier, while 16:10 is 50 minutes earlier. The exact shift is unresolved.')

assert len(CASES) == 120, len(CASES)
assert collections.Counter(c['category'] for c in CASES) == {R:30,C:30,P:30,T:30}
assert len({c['scenario_id'] for c in CASES}) == 120
for case in CASES:
    input_bytes = len(json.dumps({'question':case['question'],'evidence':case['evidence'],'history':case['history']}, ensure_ascii=False).encode())
    assert input_bytes < 1200, (case['request_id'],input_bytes)
    assert case['rubric']['required'] and case['rubric']['reference_answer']
path = Path(__file__).with_name('dataset.json')
path.write_text(json.dumps(CASES, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'path':str(path),'cases':len(CASES),'strata':dict(collections.Counter(c['category'] for c in CASES)),
                  'status':dict(collections.Counter(c['evidence_status'] for c in CASES)),
                  'max_question_evidence_history_bytes':max(len(json.dumps({'question':c['question'],'evidence':c['evidence'],'history':c['history']},ensure_ascii=False).encode()) for c in CASES)},indent=2))
