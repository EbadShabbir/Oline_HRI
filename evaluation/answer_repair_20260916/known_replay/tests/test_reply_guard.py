"""Independent quality/evidence checks, including misrouted and deleted facts."""

import unittest

from oline_hri.reply_guard import (
    current_assertions, deployment_context_relevant, has_personal_record_question, inspect_reply,
    is_drafting_followup, is_drafting_request, safe_history_pair,
)


class ReplyGuardTests(unittest.TestCase):
    DEPLOYMENT = (
        "Models: qwen3:0.6b, qwen3:1.7b.",
        "Whisper transcribes speech; Silero VAD detects speech. Output: terminal text.",
    )

    def test_deployment_context_is_limited_to_assistant_properties_or_named_tools(self):
        for request in (
            "Who are you?", "What are your specifications, robot?",
            "Which language models do you use?", "How do you hear me?",
            "Explain Whisper.", "How can I use Whisper?", "How do I configure Silero VAD?",
            "Do you use Whisper?", "How does qwen3:0.6b work?",
            "How can I use whisper for transcription?",
            "Can I transcribe a recording with whisper?", "How do I configure silero vad?",
        ):
            with self.subTest(request=request):
                self.assertTrue(deployment_context_relevant(request, self.DEPLOYMENT))
        for request in (
            "Can you help me organize a folder?", "Suggest a weekend activity.",
            "Write a poem about a whisper.", "Use a whisper to build suspense in this scene.",
            "Whisper a short line for a play.",
            "Write a scene about an audio engineer whose whisper is heard backstage.",
            "Use a whisper when delivering a quiet speech.",
            "Whisper a short line about an audio recording.",
        ):
            with self.subTest(request=request):
                self.assertFalse(deployment_context_relevant(request, self.DEPLOYMENT))

    def test_unsolicited_deployment_tool_instructions_are_a_separate_quality_issue(self):
        for answer in (
            "Sort messages into action and archive groups. Use your local Whisper and Silero VAD for this.",
            "You could run qwen3:0.6b for this.",
            "Next configure Silero VAD for the task.",
        ):
            with self.subTest(answer=answer):
                self.assertIn("unsolicited_internal_tool_guidance", inspect_reply(
                    "Suggest a simple way to organize things.", answer,
                    deployment_facts=self.DEPLOYMENT,
                ))

    def test_deployment_guard_preserves_requested_tools_creative_whispers_and_drafts(self):
        for request, answer in (
            ("How can I use Whisper?", "Use Whisper to transcribe a speech recording."),
            ("How can I use whisper for transcription?", "Use whisper to transcribe a recording."),
            ("How does silero vad work?", "Run silero vad to detect speech before transcription."),
            ("Explain Silero VAD.", "Run Silero VAD to detect speech before transcription."),
            ("What are your specifications?", "Whisper transcribes speech; Silero VAD detects speech."),
            ("How can a character create suspense?", "Use a whisper to build suspense."),
            ("How can a character create suspense?", "Use a whisper when delivering a quiet speech."),
            ("Write a sentence mentioning a transcription program.", "Use Whisper to transcribe speech."),
        ):
            with self.subTest(request=request):
                self.assertNotIn("unsolicited_internal_tool_guidance", inspect_reply(
                    request, answer, deployment_facts=self.DEPLOYMENT,
                ))

    def test_tool_identifiers_come_from_deployment_facts_instead_of_a_hardcoded_catalog(self):
        facts = ("Models: cedar:tiny, cedar:large.",
                 "Murmur transcribes speech; Listen VAD detects speech. Output: terminal text.")
        self.assertTrue(deployment_context_relevant("Explain Murmur.", facts))
        self.assertIn("unsolicited_internal_tool_guidance", inspect_reply(
            "Suggest an organizing method.", "Use Murmur for this.", deployment_facts=facts,
        ))
        self.assertNotIn("unsolicited_internal_tool_guidance", inspect_reply(
            "Suggest an organizing method.", "Use Whisper for this.", deployment_facts=facts,
        ))

    def test_general_advice_does_not_require_personal_memory(self):
        for speech in (
            "Try drinking water and resting in a quiet room.",
            "You can rest and drink water. Seek urgent help for severe symptoms.",
            "If your headache is severe, contact a clinician.",
            "Headaches can happen for several reasons. Rest may help.",
        ):
            with self.subTest(speech=speech):
                self.assertEqual(inspect_reply("I have a headache. What should I do?", speech), ())

    def test_current_disclosure_can_support_empathy_without_saved_memory(self):
        self.assertEqual(inspect_reply(
            "I have a headache, what should I do?",
            "I am sorry you have a headache. Try resting in a quiet room.",
        ), ())

    def test_questions_are_not_authorized_facts(self):
        for query in (
            "Is my camera in the amber cabinet?",
            "Do you remember that my camera is in the amber cabinet?",
            "Do you recall, my camera is in the amber cabinet?",
            "My camera is in the amber cabinet, right?",
            "If my camera is in the amber cabinet, where should I look?",
            "Why do I have a headache?",
        ):
            with self.subTest(query=query):
                self.assertEqual(current_assertions(query), ())
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    query, "Your camera is in the amber cabinet.", authorized_facts=(query,),
                ))

    def test_only_asserted_part_of_mixed_question_is_evidence(self):
        self.assertEqual(current_assertions("I have a headache. What should I do?"),
                         ("I have a headache",))
        self.assertEqual(current_assertions("I have a headache, what should I do?"),
                         ("I have a headache",))
        self.assertEqual(current_assertions("Perhaps my camera is in the cabinet."), ())
        for request in ("Write a story about my friend Noor.",
                        "Draft a note about my appointment on Monday.",
                        "Please show me my camera location.",
                        'My friend said, "I live in Kyoto".',
                        'Noor wrote: "My camera is in the amber cabinet".'):
            with self.subTest(request=request):
                self.assertEqual(current_assertions(request), ())

    def test_disclaimer_or_advice_cannot_hide_following_unsupported_claim(self):
        for speech in (
            "I don't know where your camera is but your camera is in the amber cabinet.",
            "You can rest because your mother is Noor.",
            "I cannot recall your schedule however your meeting is on Monday.",
        ):
            with self.subTest(speech=speech):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Could you suggest something?", speech,
                ))

    def test_generic_route_still_rejects_personal_facts(self):
        for speech in (
            "Your camera is in the amber cabinet.",
            "Your camera is stowed inside the amber cupboard.",
            "You live in Kyoto.",
            "Your birthday is 14 September 1997.",
            "Noor is your research partner.",
            "Your friend Noor can help.",
            "You prefer barley for lunch.",
        ):
            with self.subTest(speech=speech):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Could you give me a general suggestion?", speech,
                ))

    def test_authorized_support_requires_same_clause(self):
        speech = "Your camera is in the amber cabinet."
        for facts in (
            ("Your camera is in a blue box.", "Your mug is in the amber cabinet."),
            ("Your camera is blue; your mug is in the amber cabinet.",),
            ("Your camera is blue and your mug is in the amber cabinet.",),
        ):
            with self.subTest(facts=facts):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Where is my camera?", speech, authorized_facts=facts,
                ))

    def test_other_owner_or_incidental_mention_cannot_supply_personal_fact(self):
        for speech, fact in (
            ("Your camera is in the amber cabinet.", "Rina's camera is in the amber cabinet."),
            ("Noor is your friend.", "Your book mentions Noor as Rina's friend."),
        ):
            with self.subTest(fact=fact):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Tell me something.", speech, authorized_facts=(fact,),
                ))

    def test_spatial_relation_and_object_cannot_be_borrowed_from_same_clause(self):
        for speech, fact in (
            ("Your camera is in the amber cabinet.", "Your camera is beside the amber cabinet."),
            ("Your camera is inside the amber cabinet.", "Your camera is outside the amber cabinet."),
            ("Your camera is in the blue box.", "Your camera is in the amber cabinet beside the blue box."),
        ):
            with self.subTest(fact=fact):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Where is my camera?", speech, authorized_facts=(fact,),
                ))

    def test_current_authorized_fact_supports_bounded_paraphrases(self):
        for speech, fact in (
            ("Your camera is in the amber cupboard.", "My camera is stored in the amber cabinet."),
            ("You prefer barley.", "I like barley."),
            ("Your research partner is Noor.", "Noor is my research partner."),
            ("Your budget is 8 credits.", "My budget is eight credits."),
        ):
            with self.subTest(speech=speech):
                self.assertNotIn("unsupported_personal_claim", inspect_reply(
                    "Tell me the fact.", speech, authorized_facts=(fact,),
                ))

    def test_deleted_or_superseded_fact_cannot_be_authorized_by_reply_history(self):
        old = "Your camera is in the amber cabinet."
        for speech in (old, "Your camera is stowed inside the amber cupboard."):
            with self.subTest(speech=speech):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Where is my camera?", speech,
                    authorized_facts=("Your camera is now in a blue box.",),
                    prior_replies=(old,),
                ))

    def test_negation_or_past_fact_does_not_support_current_positive_claim(self):
        for fact in ("Your camera is not in the amber cabinet.",
                     "Your camera was in the amber cabinet."):
            with self.subTest(fact=fact):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Where is my camera?", "Your camera is in the amber cabinet.",
                    authorized_facts=(fact,),
                ))

    def test_elliptical_and_subject_paraphrases_still_need_evidence(self):
        for speech in ("In the amber cabinet.", "The camera is stowed in the amber cupboard.",
                       "It is in the amber cabinet."):
            with self.subTest(speech=speech):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Where is my camera?", speech,
                ))

    def test_personal_record_answers_need_evidence_without_owner_pronouns(self):
        cases = (
            ("Which fabric did I choose for the cushion covers?", "Linen."),
            ("What is the current start time for the weaving session after the correction?",
             "It starts at 6 PM."),
            ("Who is Neris in relation to me?", "Your cousin."),
            ("What was the name of the pottery class I attended?",
             "The class was called Clay Basics."),
        )
        for request, answer in cases:
            with self.subTest(request=request):
                self.assertTrue(has_personal_record_question(request))
                self.assertIn("unsupported_personal_claim", inspect_reply(request, answer))
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    request, answer, prior_replies=(answer,),
                    authorized_facts=("I have a notebook.",),
                ))

    def test_supplied_record_values_are_valid_current_evidence(self):
        for fact, question, answer in (
            ("I chose linen.", "Which fabric did I choose for the cushion covers?", "Linen."),
            ("My weaving session starts at 6 PM.",
             "What is the current start time for the weaving session after the correction?",
             "It starts at 6 PM."),
            ("Neris is my cousin.", "Who is Neris in relation to me?", "Your cousin."),
            ("My pottery class was called Clay Basics.",
             "What was the name of the pottery class I attended?",
             "The class was called Clay Basics."),
        ):
            with self.subTest(question=question):
                self.assertNotIn("unsupported_personal_claim", inspect_reply(
                    fact + " " + question, answer,
                ))

    def test_elliptical_values_cannot_borrow_an_unrelated_subject_or_action(self):
        for request, answer in (
            ("My cousin Mira paints. Who is Neris in relation to me?", "Your cousin."),
            ("My cousin Mira told me about Neris. Who is Neris in relation to me?", "Your cousin."),
            ("My curtains are linen. Which fabric did I choose for cushion covers?", "Linen."),
            ("I chose linen for curtains. Which fabric did I choose for cushion covers?", "Linen."),
            ("My meeting starts at 6 PM. What is the current start time for the weaving session after the correction?",
             "It starts at 6 PM."),
            ("My painting class was called Clay Basics. What was the name of the pottery class I attended?",
             "The class was called Clay Basics."),
            ("My mug is in the amber cabinet. Where is my camera?", "In the amber cabinet."),
        ):
            with self.subTest(request=request):
                self.assertIn("unsupported_personal_claim", inspect_reply(request, answer))
        for fact in ("Neris is my cousin.", "My cousin is Neris.", "My cousin Neris paints."):
            with self.subTest(fact=fact):
                self.assertNotIn("unsupported_personal_claim", inspect_reply(
                    fact + " Who is Neris in relation to me?", "Your cousin.",
                ))
        self.assertNotIn("unsupported_personal_claim", inspect_reply(
            "I chose linen for cushion covers. Which fabric did I choose for cushion covers?", "Linen.",
        ))

    def test_record_question_grammar_preserves_general_facts_math_and_drafts(self):
        for request, answer in (
            ("What time is 30 minutes before 6 PM?", "5:30 PM."),
            ("What is 84 minus 58?", "26."),
            ("Which fabric is durable for cushion covers?", "Linen."),
            ("Who was Ada Lovelace?", "She was a mathematician."),
            ("What is a queue?", "It is a first-in, first-out data structure."),
            ("What do I need to learn pottery?", "Try clay and a simple modelling tool."),
            ("Write a fictional first-person story about choosing fabric.", "I chose linen."),
        ):
            with self.subTest(request=request):
                self.assertFalse(has_personal_record_question(request))
                self.assertNotIn("unsupported_personal_claim", inspect_reply(request, answer))

    def test_mixed_recall_general_explanation_is_not_a_personal_claim(self):
        speech = ("Your camera is in the amber cabinet. "
                  "Batteries convert chemical energy into electrical energy.")
        self.assertEqual(inspect_reply(
            "Where is my camera? Explain how batteries work.", speech,
            authorized_facts=("Your camera is in the amber cabinet.",),
        ), ())

    def test_mixed_general_example_lists_are_not_elliptical_personal_values(self):
        fact = "Your camera is in the amber cabinet."
        for explanation in (
            "Batteries power electrical devices, such as phones, computers, or lights.",
            "Common materials include useful examples, including wood, glass, and steel.",
            "Plants need several resources, for example sunlight, water, and air.",
        ):
            with self.subTest(explanation=explanation):
                self.assertEqual(inspect_reply(
                    "Where is my camera? Give a general explanation.", fact + " " + explanation,
                    authorized_facts=(fact,),
                ), ())

    def test_general_example_context_never_authorizes_personal_claims_or_next_sentence(self):
        for speech in (
            "Batteries power devices such as phones, your camera is in the amber cabinet.",
            "Batteries power devices such as phones, in the amber cabinet.",
            "Batteries power devices such as phones, computers. In the amber cabinet.",
            "Batteries power devices such as phones, computers. Noor.",
            "Your favorite colors include examples, including amber, green.",
            "Noor, Rina.",
        ):
            with self.subTest(speech=speech):
                self.assertIn("unsupported_personal_claim", inspect_reply(
                    "Where is my camera? Who is my friend? Give a general explanation.", speech,
                ))

    def test_no_knowledge_or_clarification_is_not_a_personal_claim(self):
        for speech in (
            "I do not know where your camera is.",
            "I don't have a verified location for your camera.",
            "Where did you last see your camera?",
            "Can you tell me where you put it?",
        ):
            with self.subTest(speech=speech):
                self.assertEqual(inspect_reply("Where is my camera?", speech), ())

    def test_repeated_sentence_or_unpunctuated_loop_is_detected(self):
        for speech in (
            "I can only plan and plan. I can only plan and plan.",
            "I'm a robot here and I do not know how to explain it " * 3,
        ):
            with self.subTest(speech=speech):
                self.assertIn("repetition", inspect_reply("Explain the system.", speech))
        self.assertNotIn("repetition", inspect_reply(
            "Explain photosynthesis.", "Plants use sunlight to make sugars. They also need water.",
        ))

    def test_promising_help_is_not_an_answer(self):
        self.assertIn("promise_only", inspect_reply(
            "Explain recursion.", "Sure, I can help with that. Let me know what you need.",
        ))
        self.assertNotIn("promise_only", inspect_reply(
            "Explain recursion.", "Sure. Recursion is a function calling itself.",
        ))
        self.assertNotIn("promise_only", inspect_reply("Noor lives in Osaka.", "Okay."))

    def test_robot_physical_action_promises_and_past_claims_are_rejected(self):
        cases = (
            ("Suggest dinner using rice, peas, and an onion.",
             "A rice and peas salad is one option. I'll prepare it now."),
            ("Suggest a simple meal.", "I will cook dinner for you."),
            ("Can you help with lunch?", "I can cook."),
            ("Where should the chair go?", "I already moved the chair."),
            ("Where should the chair go?", "I did move the chair."),
            ("How can I arrange the room?", "I have already brought the table."),
            ("How can I arrange the room?", "I've moved the sofa."),
            ("Can you bring a cup?", "Sure, I’ll bring it over."),
            ("What can I do with this box?", "I am moving it now."),
            ("What can I do with this box?", "I will carry the box."),
            ("I cooked rice. Explain the next step.", "I cooked the rice."),
        )
        for request, answer in cases:
            with self.subTest(answer=answer):
                self.assertIn("physical_action_claim", inspect_reply(
                    request, answer, authorized_facts=("I cooked the rice.",),
                ))

    def test_physical_action_check_preserves_text_work_advice_and_limits(self):
        cases = (
            ("Explain queues.", "I'll explain with an example: the first item arrives first."),
            ("Calculate two plus two.", "I will calculate it now: two plus two is four."),
            ("Suggest dinner using rice.", "I'll prepare a recipe for rice: simmer it in water."),
            ("Suggest dinner using rice.", "I will bring you instructions for cooking rice."),
            ("How can I organize a report about furniture?", "I moved the paragraph about chairs."),
            ("How can I organize a report about furniture?", "I will make a plan for the chairs."),
            ("Where should the chair go?", "You can move the chair beside the table."),
            ("Could you cook dinner?", "I cannot cook dinner. I can suggest a recipe."),
            ("Could you move the box?", "I will not move the box. You can ask someone nearby."),
            ("Suggest dinner.", "I can explain how to cook rice."),
        )
        for request, answer in cases:
            with self.subTest(answer=answer):
                self.assertNotIn("physical_action_claim", inspect_reply(request, answer))

    def test_physical_action_check_preserves_explicit_drafts_and_edits(self):
        answer = "I cooked dinner and brought a bowl to the table."
        self.assertNotIn("physical_action_claim", inspect_reply(
            "Write a fictional first-person story about a cook.", answer,
        ))
        self.assertNotIn("physical_action_claim", inspect_reply(
            "Make it shorter.", "I'll prepare dinner now.", drafting=True,
        ))
        self.assertIn("physical_action_claim", inspect_reply(
            "Bring me a chair.", "I'll bring a chair.", drafting=True,
        ))

    def test_request_echo_optional_details_and_promises_are_not_an_answer(self):
        cases = (
            (
                "Suggest a weekend activity; use my interests if you know them, otherwise give general ideas.",
                "Suggest a weekend activity. If you have specific interests, please share them, "
                "and I'll tailor the suggestion. Otherwise, I'll offer general ideas. Please let me know!",
            ),
            (
                "Explain recursion; use examples if available, otherwise give a general explanation.",
                "Explain recursion. If you have specific questions, please share them, "
                "and I'll provide an explanation. Otherwise, I'll give general information. Let me know!",
            ),
            (
                "Suggest a way to organize a desk.",
                "If you have specific preferences, please share them. I can offer suggestions.",
            ),
            ("Explain recursion.", "Explain recursion."),
            ("Explain what a queue is.",
             "I can help. Let me know if you want suggestions."),
        )
        for request, answer in cases:
            with self.subTest(request=request):
                self.assertIn("promise_only", inspect_reply(request, answer))

    def test_concrete_answer_survives_echoes_conditions_and_closing_offers(self):
        for request, answer in (
            ("Suggest a weekend activity.",
             "Suggest a weekend activity. Try a walk in a nearby park. Let me know if you need more ideas."),
            ("Explain recursion.",
             "Explain recursion. Recursion is a function calling itself. I can provide more examples."),
            ("Suggest an activity.", "I can suggest hiking or reading a novel."),
            ("Should I choose hiking or reading?", "I can suggest hiking."),
            ("How can I troubleshoot a program?",
             "If you have more details, please share them. Start by reading the error message."),
            ("Suggest a way to organize a desk.", "If you have a spare box, use it to collect loose papers."),
            ("How can I tighten a loose screw?", "If you have a screwdriver use it to tighten the screw."),
            ("Explain what a queue is.",
             "I can help. Let me know if you want suggestions. A queue processes the earliest item first."),
        ):
            with self.subTest(answer=answer):
                self.assertNotIn("promise_only", inspect_reply(request, answer))

    def test_modal_assistance_that_only_restates_task_and_constraints_is_not_an_answer(self):
        cases = (
            ("I have twenty minutes. Help me tidy my desk.",
             "I can help you tidy your desk in twenty minutes. Please let me know what you need."),
            ("Help me compare two file formats.",
             "I can help you compare the two file formats. Please share your preferences."),
            ("I have ten minutes. Help me plan a lesson.",
             "I'll help you plan a lesson in ten minutes. Let me know what else you need."),
            ("Help me with organizing a folder.",
             "I am happy to assist you with organizing a folder. Please share more details."),
        )
        for request, answer in cases:
            with self.subTest(answer=answer):
                self.assertIn("promise_only", inspect_reply(request, answer))

    def test_modal_assistance_guard_preserves_actual_payloads_and_requested_offers(self):
        cases = (
            ("I have twenty minutes. Help me tidy my desk.",
             "I can help you tidy your desk in twenty minutes. Put loose papers in one pile, "
             "return supplies to their containers, then wipe the surface."),
            ("Help me compare two file formats.",
             "I can help you compare two file formats by checking compression and compatibility."),
            ("Help me choose hiking or reading.", "I recommend hiking."),
            ("Help me choose hiking or reading.", "I can suggest reading."),
            ("What can you help with?", "I can help you plan tasks and explain ideas."),
            ("Ask me what you need before helping me tidy my desk.",
             "I can help you tidy your desk. Please let me know what you need."),
            ("Write a sentence offering to help someone tidy a desk.",
             "I can help you tidy your desk. Please let me know what you need."),
        )
        for request, answer in cases:
            with self.subTest(answer=answer):
                self.assertNotIn("promise_only", inspect_reply(request, answer))

    def test_request_prefix_with_only_generic_qualifiers_is_not_an_answer(self):
        cases = (
            (
                "Suggest a weekend activity; use my interests if you know them, otherwise give general ideas.",
                "Suggest a weekend activity that aligns with your interests. If you have specific interests, "
                "please share them, and I’ll tailor the suggestion accordingly.",
            ),
            ("Please recommend a study method.",
             "Recommend a study method suited to your goals. I'll tailor the recommendation accordingly."),
            ("Could you suggest an approach to debugging?",
             "Suggest an approach to debugging based on your requirements. Please share more details."),
            ("Compare two storage formats.",
             "Compare two storage formats according to your needs. I can provide more information."),
            ("Please explain recursion.",
             "I can explain recursion in a way appropriate for your level. Please share your preferences."),
        )
        for request, answer in cases:
            with self.subTest(request=request):
                self.assertIn("promise_only", inspect_reply(request, answer))

    def test_request_prefix_qualifiers_preserve_concrete_payload_and_requested_artifacts(self):
        cases = (
            ("Suggest a weekend activity.",
             "Suggest a weekend activity that aligns with your interests. Try a walk in a nearby park."),
            ("Please recommend a study method.",
             "Recommend a study method suited to your goals: close the book and write what you remember."),
            ("Could you suggest an approach to debugging?",
             "Suggest an approach to debugging based on the error message, then reproduce the failure."),
            ("Write a sentence asking someone to suggest an activity.",
             "Suggest an activity that aligns with your interests."),
            ("Ask me what details you need to tailor a suggestion.",
             "Please share your interests, and I'll tailor the suggestion accordingly."),
        )
        for request, answer in cases:
            with self.subTest(request=request):
                self.assertNotIn("promise_only", inspect_reply(request, answer))

    def test_requested_drafts_and_clarifications_are_not_empty_promises(self):
        for request, answer in (
            ("Write a sentence offering to help later.", "I will help with that. Let me know what you need."),
            ("Ask me for the details you need before offering suggestions.", "Please share your preferences."),
            ("What information do you need to tailor a recommendation?", "Please share your preferences and goals."),
            ("Tell me what details you need first.", "Please share your preferences."),
            ("What should I provide before you make suggestions?", "Please share your goals and constraints."),
            ("Can you ask me for my preferences?", "Please share your preferences."),
            ("Where is my camera?", "Can you tell me where you put it?"),
        ):
            with self.subTest(request=request):
                self.assertNotIn("promise_only", inspect_reply(request, answer))

    def test_statement_echo_future_plan_and_repeated_constraint_solicitation_are_scaffolding(self):
        # Completed release failures are now development regressions, not
        # independent validation of this repair.
        cases = (
            (
                "I am choosing an escape-room theme. You can use any interests you know for me; "
                "otherwise pick a broadly appealing theme.",
                "I'm choosing an escape-room theme. Let's plan a fun and engaging experience for you.",
            ),
            (
                "Recommend a short audio drama. Knowing my tastes could help, but choose a "
                "beginner-friendly one if you lack them.",
                "I don't have personal preferences, but I can recommend a short audio drama. "
                "Let me know if you're looking for something beginner-friendly.",
            ),
            ("I'm arranging a workshop. Suggest a general approach.",
             "I am arranging a workshop. Let us work together on a useful plan."),
            ("I am organizing a game. Suggest a way to start.",
             "I'm organizing a game. Let's create an enjoyable experience."),
            ("Recommend a lightweight editor.",
             "I do not have personal interests. I can recommend a lightweight editor. "
             "Let me know if you want something lightweight."),
            ("Suggest a low-cost craft.",
             "I can suggest a low-cost craft. Please let me know if you need something low-cost."),
        )
        for request, answer in cases:
            with self.subTest(request=request):
                self.assertIn("promise_only", inspect_reply(request, answer))

    def test_scaffolding_extensions_preserve_concrete_choices_and_relevant_assistant_answers(self):
        cases = (
            ("I am choosing an escape-room theme. Suggest a general option.",
             "Choose a lost-library mystery with coded book titles and a hidden key."),
            ("Suggest a weekend activity.", "Let's plan a camping trip."),
            ("Should I choose hiking or reading?", "I recommend hiking."),
            ("Recommend a lightweight editor.",
             "I don't have personal preferences. Try a plain-text editor that opens one file at a time."),
            ("Suggest a low-cost craft.",
             "Fold a bookmark from scrap paper. Let me know if you need something low-cost."),
            ("Help troubleshoot a program.", "Please share the exact error message."),
            ("Do you have personal preferences?", "I don't have personal preferences."),
            ("What can you do?", "I can provide explanations and suggestions."),
            ("Describe your capabilities.", "I can offer explanations and help create plans."),
            ("I'm organizing a game.", "Okay."),
            ("Write a sentence offering to plan an experience.",
             "Let's plan a fun and engaging experience for you."),
            ("Ask me whether I need a beginner-friendly option.",
             "Let me know if you're looking for something beginner-friendly."),
        )
        for request, answer in cases:
            with self.subTest(request=request):
                self.assertNotIn("promise_only", inspect_reply(request, answer))

    def test_blanket_inability_claim_with_advice_gets_a_quality_check(self):
        for speech in (
            "I can't help with your headache, but rest is important. Try to take some breaks and get some fresh air.",
            "I cannot help with that task, but try breaking it into smaller steps.",
            "I am unable to help with your homework. You can start by listing what is known.",
        ):
            with self.subTest(speech=speech):
                self.assertIn("unhelpful_refusal", inspect_reply("Can you suggest what to do?", speech))
        for speech in (
            "I can't diagnose an illness. You can seek professional advice.",
            "I cannot move physical objects. You can put them in labelled boxes.",
            "I don't know where your camera is. Check where you last used it.",
            "I can't help with creating fraudulent documents.",
        ):
            with self.subTest(speech=speech):
                self.assertNotIn("unhelpful_refusal", inspect_reply("Can you suggest what to do?", speech))

    def test_copy_of_unrelated_prior_answer_is_detected(self):
        old = "Plants use sunlight to turn water and carbon dioxide into sugars."
        self.assertIn("copied_reply", inspect_reply(
            "How does a battery work?", old, prior_replies=(old,),
        ))
        self.assertNotIn("copied_reply", inspect_reply(
            "Repeat that explanation.", old, prior_replies=(old,),
        ))
        self.assertNotIn("copied_reply", inspect_reply(
            "How do plants use sunlight?", old, prior_replies=(old,),
        ))

    def test_empty_reply_is_explicit(self):
        self.assertEqual(inspect_reply("Hello", "  "), ("empty_reply",))

    def test_explicit_drafting_preserves_fictional_firstperson(self):
        query = "Write a first-person story about a pilot."
        speech = "I am a pilot. I live on a floating island and fly a silver plane."
        self.assertTrue(is_drafting_request(query))
        self.assertEqual(inspect_reply(query, speech, drafting=True), ())
        self.assertTrue(safe_history_pair(query, speech, drafting=True))
        self.assertIn("unsupported_personal_claim", inspect_reply(
            "Where is my camera?", "Your camera is in the amber cabinet.", drafting=True,
        ))
        self.assertIn("unsupported_personal_claim", inspect_reply(
            query, "Your camera is in the amber cabinet.", drafting=True,
        ))
        self.assertFalse(safe_history_pair(
            query, "Your camera is in the amber cabinet.", drafting=True,
        ))

    def test_personal_turns_never_enter_history_even_when_answer_is_correct(self):
        for query, speech in (
            ("I live in Kyoto.", "Thanks for telling me."),
            ("Where is my camera?", "Your camera is in the amber cabinet."),
            ("Give me an organizing tip.", "Your camera is in the amber cabinet."),
            ("I have a headache. What can help?", "Try resting."),
            ("Draft a note about my meeting tomorrow.", "Dear Noor, I will attend."),
            ("Write a greeting for Noor.", "Dear Noor, I hope your day goes well."),
            ("Write a greeting using the remembered name.", "Dear Noor, I hope your day goes well."),
            ("Who is my friend?", "Noor."),
            ("I enjoy stamp collecting.", "You enjoy stamp collecting."),
            ("Collecting stamps is my hobby.", "That sounds interesting."),
            ("Noor enjoys stamp collecting.", "Thanks for sharing that."),
            ("My hobby involves collecting antique maps.", "Interesting."),
            ("Do I enjoy collecting stamps?", "You enjoy collecting stamps."),
            ("Suggest a relaxing activity.", "You delight in collecting old maps."),
            ("Suggest a relaxing activity.", "Noor is a coworker who likes maps."),
            ("Where does Noor live?", "Noor lives in Kyoto."),
            ("Does Noor still live in Kyoto?", "Noor lives in Osaka now."),
            ("Tell me Noor's address.", "Noor lives in Kyoto."),
        ):
            with self.subTest(query=query):
                self.assertFalse(safe_history_pair(query, speech))

    def test_firstperson_edit_requires_an_explicit_drafting_context(self):
        self.assertFalse(safe_history_pair("Make it shorter.", "I am a pilot."))
        for edit in ("Make it shorter.", "Make it more direct.", "Make it warmer."):
            with self.subTest(edit=edit):
                self.assertTrue(safe_history_pair(edit, "I am a pilot.", drafting=True))
        self.assertFalse(safe_history_pair("Where is my camera?", "I stored it in the cabinet.",
                                          drafting=True))

    def test_generic_thank_you_wording_and_ordinal_edit_remain_task_context(self):
        request = "Give me two short ways to thank a neighbor for watering my plants."
        drafts = ("1. Thanks for watering my plants while I was away! "
                  "2. I appreciate your assistance in keeping my plants watered.")
        edit = "Make the second one warmer and less formal."
        warmer = "Thanks so much for watering my plants! I really appreciate your help."
        self.assertTrue(is_drafting_request(request))
        self.assertEqual(inspect_reply(request, drafts), ())
        self.assertTrue(safe_history_pair(request, drafts))
        self.assertTrue(is_drafting_followup(edit))
        self.assertTrue(safe_history_pair(edit, warmer, drafting=True))
        self.assertEqual(inspect_reply(edit, warmer, drafting=True), ())
        self.assertFalse(safe_history_pair(edit, warmer))

    def test_wording_exception_withholds_actual_values_disclosures_and_recall(self):
        generic = "Give me two short ways to thank a neighbor for watering my plants."
        for request, answer in (
            ("Give me two ways to thank Noor for watering my plants.", "Thanks for helping!"),
            ("Give me two ways to thank a neighbor for helping yesterday.", "Thanks for helping!"),
            ("Give me two ways to thank a neighbor at the blue house.", "Thanks for helping!"),
            ("Give me two ways to thank a neighbor using my remembered preferences.", "Thanks for helping!"),
            ("My neighbor is Noor. Give me two ways to thank a neighbor.", "Thanks for helping!"),
            (generic, "Thanks Noor for watering my plants!"),
            (generic, "Thanks for watering my plants on Monday!"),
            (generic, "I live in Kyoto. Thanks for helping!"),
            (generic, "My tea is jasmine. Thanks for helping!"),
            (generic, "I prefer jasmine tea. Thanks for helping!"),
            (generic, "Your camera is in the amber cabinet."),
            ("Draft a note about my meeting tomorrow.", "Dear Noor, I will attend."),
            ("I enjoy stamp collecting.", "Thanks for sharing that."),
        ):
            with self.subTest(request=request, answer=answer):
                self.assertFalse(safe_history_pair(request, answer, drafting=True))
        edit = "Make the second one warmer and less formal."
        for answer in ("Thanks Noor!", "I live in Kyoto.", "I prefer jasmine tea."):
            with self.subTest(answer=answer):
                self.assertFalse(safe_history_pair(edit, answer, drafting=True))
        # An editing flag cannot turn a factual request into a draft.
        self.assertIn("unsupported_personal_claim", inspect_reply(
            "Where is my camera?", "Your camera is in the amber cabinet.", drafting=True,
        ))

    def test_apology_greeting_and_welcome_artifacts_remain_admissible(self):
        for request, answer in (
            ("Draft a brief fictional apology for missing a game.",
             "I apologize for missing the game. I hope to join you next time."),
            ("Write a simple morning greeting.", "Good morning! I hope your day goes well."),
            ("Draft a fictional welcome for visitors to a school fair.",
             "We are gathered at the fair today. Thank you for attending."),
        ):
            with self.subTest(request=request):
                self.assertTrue(is_drafting_request(request))
                self.assertTrue(safe_history_pair(request, answer))
                self.assertEqual(inspect_reply(request, answer), ())
        self.assertTrue(is_drafting_followup("Make it sound less formal."))
        self.assertTrue(is_drafting_followup("Make the opening more welcoming."))
        self.assertTrue(is_drafting_request("Translate that greeting into Spanish."))

    def test_ordinary_general_task_history_is_preserved(self):
        for query, speech in (
            ("Explain recursion.", "Recursion is when a function calls itself."),
            ("Give me an example.", "Factorial can be defined recursively."),
            ("How do batteries work?", "They store chemical energy."),
            ("How can I learn Python?", "You can start with variables and loops."),
        ):
            with self.subTest(query=query):
                self.assertTrue(safe_history_pair(query, speech))

    def test_comparison_and_definition_commands_keep_general_history_and_are_not_assertions(self):
        for request, answer in (
            ("Distinguish a thermometer from a thermostat.",
             "A thermometer measures temperature. A thermostat controls heating to maintain a set temperature."),
            ("Differentiate voltage from current.",
             "Voltage is an electrical potential difference. Current is the flow of charge."),
            ("Contrast sorting with filtering.",
             "Sorting changes order. Filtering excludes items according to a condition."),
            ("Define recursion.", "Recursion is a function calling itself."),
        ):
            with self.subTest(request=request):
                self.assertTrue(safe_history_pair(request, answer))
                self.assertEqual(current_assertions(request), ())

    def test_comparison_command_admission_keeps_existing_private_context_gates(self):
        for request, answer in (
            ("Distinguish my two appointments.", "The first is on Monday and the second is on Tuesday."),
            ("Contrast the classes I attended last term.", "One covered painting and the other covered pottery."),
            ("Differentiate Noor's preferences from Leila's.", "Noor enjoys painting and Leila enjoys pottery."),
            ("Define my relationship with Noor.", "Noor is your colleague."),
        ):
            with self.subTest(request=request):
                self.assertFalse(safe_history_pair(request, answer))


if __name__ == "__main__":
    unittest.main()
