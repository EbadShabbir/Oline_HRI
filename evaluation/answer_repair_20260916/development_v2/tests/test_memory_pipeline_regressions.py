"""Synthetic evidence-boundary regressions; no model accuracy measurements."""

from dataclasses import replace
from datetime import datetime, timezone, timedelta
import unittest

from oline_hri.config import load_config
from oline_hri.conversation import Conversation, _conflicting_labels, _required_memory_ids, _verified_composed_answer
from oline_hri.grounded_composition import AnswerFact, compose_verified_event_times
from oline_hri.response import ResponseValidationError
from tests.test_conversation_routed import FakeBackend, FakeRetriever, FakeRouter, chat_result, hybrid_match, memory, routing_result
from tests.test_grounded_composition import SchemaBackend


SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"


class MemoryPipelineRegressionTests(unittest.TestCase):
    def pipeline(self, items, *, backend=None, fixed=None, composition=True):
        backend = backend or SchemaBackend()
        retriever = FakeRetriever(tuple(hybrid_match(item, n) for n, item in enumerate(items, 1)))
        conversation = Conversation(
            backend, system_prompt=load_config().conversation.system_prompt,
            router=FakeRouter((routing_result(True, "large"),)), retriever=retriever,
            small_model=SMALL, large_model=LARGE, general_large_model=LARGE,
            fixed_generator_model=fixed, grounded_composition=composition,
        )
        return conversation, backend, retriever

    def test_numbers_units_and_calendar_overlap_never_authorize_unrelated_facts(self):
        items = (memory(901, "You prefer walking for journeys shorter than 25 minutes."),
                 memory(902, "You completed a speaker trial on 7 October 2026 at 08:00."))
        matches = tuple(hybrid_match(item) for item in items)
        for prompt in (
            "A timer starts at 08:00 and lasts 25 minutes. What time does it finish?",
            "Which event in my astronomy journal happened on 7 October 2026?",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(_required_memory_ids(matches, prompt), ())

    def test_no_linked_evidence_is_not_disclosed_in_any_generator_arm(self):
        item = memory(903, "Your weaving bag is hidden in the indigo cupboard.")
        for fixed in (None, SMALL, LARGE):
            with self.subTest(fixed=fixed):
                backend = FakeBackend((chat_result("I do not know.", model=fixed or LARGE),))
                convo, backend, _ = self.pipeline((item,), backend=backend, fixed=fixed)
                reply = convo.send("Where is my telescope case?")
                self.assertEqual(reply.memory_diagnostics.retrieved_ids, (item.id,))
                self.assertEqual(reply.memory_diagnostics.supplied_ids, ())
                self.assertEqual(reply.response.memory_used, ())
                self.assertEqual(reply.response.speech, "I do not have a verified personal memory that answers that.")
                self.assertNotIn("indigo cupboard", str(backend.calls))

    def test_calendar_value_requires_the_requested_preference_subject(self):
        meeting = memory(960, "You prefer project meetings on Thursday afternoons.")
        unrelated = memory(961, "You completed a paint trial on Thursday afternoon.")
        matches = (hybrid_match(unrelated), hybrid_match(meeting))
        self.assertEqual(_required_memory_ids(matches, "Use Thursday afternoons in a meeting plan."), (meeting.id,))

    def test_name_attribute_does_not_authorize_project_partner_or_duration(self):
        items = (memory(904, "Your sculpture project is named Cobalt."),
                 memory(905, "Your sculpture project partner is Esra."),
                 memory(906, "Your sculpture project meetings last 40 minutes."))
        self.assertEqual(_required_memory_ids(tuple(hybrid_match(item) for item in items),
                         "What is the name of my sculpture project?"), (items[0].id,))

    def test_conflicting_room_values_are_retained_and_never_silently_chosen(self):
        items = tuple(memory(910 + n, f"Your glazing demonstration on 8 November 2026 is in {room}.")
                      for n, room in enumerate(("Amber Hall", "Willow Hall", "Cypress Hall")))
        for fixed in (None, SMALL, LARGE):
            with self.subTest(fixed=fixed):
                model = fixed or LARGE
                backend = FakeBackend((chat_result("It is in Amber Hall.", memory_used=tuple(i.id for i in items), model=model),))
                convo, _, _ = self.pipeline(items, backend=backend, fixed=fixed)
                reply = convo.send("Which room is booked for my glazing demonstration on 8 November 2026?")
                self.assertEqual(set(reply.response.memory_used), {item.id for item in items})
                self.assertEqual(reply.response_transform, "conflict_clarification")
                for name in ("Amber Hall", "Willow Hall", "Cypress Hall"):
                    self.assertIn(name, reply.response.speech)
                self.assertIn("confirm", reply.response.speech)

    def test_conflict_detection_preserves_owner_event_and_negation_boundaries(self):
        original = memory(920, "Your glazing class on 8 November 2026 is in Amber Hall.")
        for other in (
            "Your glazing class on 9 November 2026 is in Willow Hall.",
            "Esra's glazing class on 8 November 2026 is in Willow Hall.",
            "Your painting class on 8 November 2026 is in Willow Hall.",
            "Your glazing class on 8 November 2026 is not in Willow Hall.",
        ):
            with self.subTest(other=other):
                self.assertEqual(_conflicting_labels((hybrid_match(original), hybrid_match(memory(921, other)))), ())
        short = replace(original, canonical_text=original.canonical_text.replace("Amber Hall", "Lab A"))
        for other in (
            "Your glazing class on 9 November 2026 is in Lab B.",
            "Esra's glazing class on 8 November 2026 is in Lab B.",
            "Your glazing class on 8 November 2026 is not in Lab B.",
        ):
            with self.subTest(short_label=other):
                self.assertEqual(_conflicting_labels((hybrid_match(short), hybrid_match(memory(922, other)))), ())

    def test_partial_direct_recall_binds_known_fact_and_explicit_unknown(self):
        item = memory(930, "You prefer millet for studio lunch.")
        prompt = "Tell me my current studio-lunch grain preference and my display flag's current location. If either is not known, identify which one."
        for fixed in (None, SMALL, LARGE):
            with self.subTest(fixed=fixed):
                convo, _, _ = self.pipeline((item,), fixed=fixed)
                reply = convo.send(prompt)
                self.assertEqual(reply.answer_constraint, "verified_partial_recall")
                self.assertIn(item.canonical_text, reply.response.speech)
                self.assertIn("do not have verified information", reply.response.speech)
                self.assertIn("display flag", reply.response.speech)
                self.assertEqual(reply.response.memory_used, (item.id,))
        backend = SchemaBackend(speech="You prefer millet. Your flag is in a purple drawer.")
        convo, _, _ = self.pipeline((item,), backend=backend)
        with self.assertRaises(ResponseValidationError):
            convo.send(prompt)
        self.assertIsNone(_verified_composed_answer((hybrid_match(item),),
            "Tell me my current studio-lunch grain preference and my display flag's current location. Give their dates and times.",
            (item.id,)))

    def event_items(self):
        return (
            replace(memory(940, "You completed the copper trial on 30 October 2026 at 23:20."),
                    event_time="2026-10-30T23:20:00.000000Z", kind="event"),
            replace(memory(941, "You completed the glass trial on 1 November 2026 at 01:05."),
                    event_time="2026-11-01T01:05:00.000000Z", kind="event"),
        )

    def test_verified_interval_preserves_both_sources_and_checks_the_result(self):
        items = self.event_items()
        prompt = "How many hours passed between my copper trial and my glass trial? Use the stored event times and show the two times."
        for fixed in (None, SMALL, LARGE):
            with self.subTest(fixed=fixed):
                convo, _, retriever = self.pipeline(items[::-1], fixed=fixed)
                reply = convo.send(prompt)
                self.assertEqual(reply.answer_constraint, "verified_event_interval")
                self.assertIn("25 hours 45 minutes", reply.response.speech)
                for item in items:
                    self.assertIn(item.canonical_text, reply.response.speech)
                self.assertEqual(set(reply.response.memory_used), {item.id for item in items})
                self.assertEqual(len(retriever.current_calls), 2)
        for backend in (SchemaBackend(speech="Only 1 hour elapsed."), SchemaBackend(citation_mode="missing")):
            convo, _, _ = self.pipeline(items, backend=backend)
            with self.assertRaises(ResponseValidationError):
                convo.send(prompt)

    def test_three_event_order_keeps_every_date_clock_and_subject(self):
        first, last = self.event_items()
        middle = replace(memory(942, "You submitted the permit form on 31 October 2026 at 12:00."),
                         event_time="2026-10-31T12:00:00.000000Z", kind="event")
        prompt = "Put my completed copper trial, permit-form submission, and completed glass trial in chronological order, giving each stored date and time."
        convo, _, _ = self.pipeline((last, first, middle))
        reply = convo.send(prompt)
        self.assertEqual(reply.answer_constraint, "verified_event_order")
        self.assertLess(reply.response.speech.index("copper"), reply.response.speech.index("permit"))
        self.assertLess(reply.response.speech.index("permit"), reply.response.speech.index("glass"))
        self.assertEqual(set(reply.response.memory_used), {first.id, middle.id, last.id})
        self.assertIsNone(_verified_composed_answer((hybrid_match(first), hybrid_match(last)), prompt,
                                                   (first.id, last.id)))

    def test_event_composer_declines_additional_tasks_and_hypothetical_changes(self):
        facts = tuple(AnswerFact(item.canonical_text, instant=datetime.fromisoformat(item.event_time.replace("Z", "+00:00")))
                      for item in self.event_items())
        for prompt in (
            "Which trial comes first after moving the glass trial five days earlier?",
            "Which comes first, my copper trial or my glass trial? Also draft a thank-you note.",
            "Which comes first, my copper trial or my glass trial? Include a checklist for getting ready.",
            "How many seconds elapsed between my copper trial and my glass trial?",
            "Put my three recorded events in chronological order.",
            "List my three completed trials chronologically.",
            "Put my copper trial, permit submission, and glass trial in chronological order.",
            "Which comes first, my copper trial or my glass trial and sing a song?",
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(compose_verified_event_times(facts, prompt))
        items = self.event_items()
        for prompt in (
            "Put my copper trial and glass trial in chronological order after moving the glass trial five days earlier.",
            "Put my copper trial and glass trial in chronological order. Also draft a thank-you note.",
            "Create a timeline after moving the glass trial five days earlier.",
        ):
            with self.subTest(integrated=prompt):
                self.assertIsNone(_verified_composed_answer(tuple(hybrid_match(item) for item in items),
                                                           prompt, tuple(item.id for item in items)))

    def test_ambiguous_or_conflicting_source_times_do_not_authorize_arithmetic(self):
        first, last = self.event_items()
        prompt = "How many hours passed between my copper trial and my glass trial?"
        for altered in (
            replace(first, event_time=None),
            replace(first, event_time="2026-10-30T22:20:00Z"),
            replace(first, event_time="2026-10-30T23:20:00+01:00"),
            replace(first, canonical_text=first.canonical_text[:-1] + " Pacific time."),
            replace(first, canonical_text=first.canonical_text[:-1] + " in Europe/Paris."),
            replace(first, canonical_text=first.canonical_text.replace("23:20", "23:20:45")),
            replace(first, canonical_text=first.canonical_text[:-1] + " CET."),
            replace(first, canonical_text=first.canonical_text[:-1] + " IST."),
            replace(first, canonical_text=first.canonical_text[:-1] + " (CET)."),
            replace(first, canonical_text=first.canonical_text.replace("23:20", "23:20(cet)")),
        ):
            with self.subTest(altered=altered):
                self.assertIsNone(_verified_composed_answer((hybrid_match(altered), hybrid_match(last)),
                                                           prompt, (first.id, last.id)))

    def test_elapsed_minutes_and_calendar_rollover_use_exact_datetime_subtraction(self):
        items = self.event_items()
        facts = tuple(AnswerFact(item.canonical_text, instant=datetime.fromisoformat(item.event_time.replace("Z", "+00:00")))
                      for item in items)
        reply = compose_verified_event_times(facts, "How many minutes elapsed between my copper trial and my glass trial?")
        self.assertIn("1545 minutes", reply.speech)
        for instant in (None, "unknown", datetime(2026, 1, 1), facts[0].instant.replace(second=1),
                        facts[0].instant.astimezone(timezone(timedelta(hours=1)))):
            with self.subTest(instant=instant):
                self.assertIsNone(compose_verified_event_times((replace(facts[0], instant=instant), facts[1]),
                    "How many minutes elapsed between my copper trial and my glass trial?"))


if __name__ == "__main__":
    unittest.main()
