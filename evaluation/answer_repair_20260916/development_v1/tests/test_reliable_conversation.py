"""Behavioral coverage for the live answerability and evidence boundary."""

from dataclasses import asdict
import json
import unittest

from oline_hri.answer_review import AnswerReview, AnswerReviewer
from oline_hri.config import load_config
from oline_hri.ollama import ChatMessage
from oline_hri.reliable_conversation import ReliableConversation, deployment_facts
from oline_hri.routing import RouteDecision
from oline_hri.semantic_routing import MemoryDependency, SemanticRoutingResult

from test_conversation_routed import (
    FakeBackend, FakeRetriever, FakeRouter, GENERAL_LARGE_MODEL, LARGE_MODEL,
    SMALL_MODEL, chat_result, hybrid_match, memory,
)


def semantic_route(mode="none", *, form="question", missing="", fragment="", size="small"):
    if mode in {"optional", "required"} and not missing:
        missing = "stored personal fact"
    if mode == "clarify":
        missing = "request context"
    dependency = MemoryDependency(form, mode, missing, fragment, False)
    return SemanticRoutingResult(
        decision=RouteDecision(mode in {"optional", "required"}, size),
        memory_required_generation=chat_result(raw=json.dumps(asdict(dependency))),
        model_size_generation=chat_result(raw=json.dumps({"model_size": size})),
        memory_decision_source="semantic_model", model_size_decision_source="semantic_model",
        dependency=dependency,
    )


class StubReviewer:
    def __init__(self, verdicts=(), *, callback=None):
        self.verdicts = list(verdicts)
        self.calls = []
        self.callback = callback

    def review(self, request, answer, *, authorized_facts=(), history=(), drafting=False,
               deployment_facts=()):
        self.calls.append({"request": request, "answer": answer,
                           "authorized_facts": tuple(authorized_facts),
                           "history": tuple(history), "drafting": drafting,
                           "deployment_facts": tuple(deployment_facts)})
        if self.callback:
            self.callback()
        verdict, reason = self.verdicts.pop(0) if self.verdicts else ("pass", "supported_answer")
        return AnswerReview(verdict, reason, chat_result(
            raw=json.dumps({"verdict": verdict, "reason": reason}), model=LARGE_MODEL,
        ))


class LifecycleRetriever(FakeRetriever):
    def __init__(self, matches):
        super().__init__(matches)
        self.live = True
        self.events = []

    def is_current(self, matches):
        self.current_calls.append(tuple(matches))
        self.events.append("snapshot")
        return self.live


class ReviewBackend(FakeBackend):
    """Accept the deterministic sampler options used by the real reviewer."""
    def chat(self, model, messages, **options):
        return super().chat(model, messages, response_format=options.get("response_format"))


def reliable(backend, *, route=None, router=None, retriever=None, reviewer=None,
             runtime_facts=()):
    router = router or FakeRouter(default=route or semantic_route())
    retriever = retriever or FakeRetriever()
    reviewer = reviewer or StubReviewer()
    session = ReliableConversation(
        backend, router=router, retriever=retriever, reviewer=reviewer,
        system_prompt="Be helpful and concise.", small_model=SMALL_MODEL,
        large_model=LARGE_MODEL, general_large_model=GENERAL_LARGE_MODEL,
        runtime_facts=runtime_facts,
    )
    return session, router, retriever, reviewer


class ReliableConversationTests(unittest.TestCase):
    def test_default_context_fits_general_and_optional_plans_with_quality_retry(self):
        config = load_config()
        request = (
            "Create a 30-minute desk-tidying plan. If you have a saved preference about "
            "how I organize tasks, adapt the steps to it; otherwise use a straightforward order. "
            "There are papers, books, cables and pens on the desk. Use separate piles, keep "
            "the walkway clear, and put items away before cleaning the surface. Do not require "
            "new storage boxes or moving furniture. Finish by checking that the desk is usable."
        )
        answer = "Sort papers and supplies, put each group away, then wipe the desk and check the walkway."
        for mode in ("none", "optional"):
            with self.subTest(mode=mode):
                backend = FakeBackend((chat_result("I can only plan. " * 6),
                                       chat_result(answer, model=LARGE_MODEL)))
                session = ReliableConversation(
                    backend, router=FakeRouter(default=semantic_route(mode)),
                    retriever=FakeRetriever(), reviewer=StubReviewer(),
                    small_model=SMALL_MODEL, large_model=LARGE_MODEL,
                    general_large_model=GENERAL_LARGE_MODEL,
                    system_prompt=config.conversation.system_prompt,
                    runtime_facts=deployment_facts(config),
                    context_length=config.generation.context_length,
                    max_output_tokens=config.generation.max_output_tokens,
                )
                reply = session.send(request)
                self.assertEqual(reply.response.speech, answer)
                self.assertEqual(reply.attempted_models, (SMALL_MODEL, LARGE_MODEL))
                self.assertEqual(len(backend.calls), 2)
                self.assertNotIn("ConversationError", reply.quality_issues)

    def test_context_preflight_failure_is_not_recorded_as_model_dispatch(self):
        backend = FakeBackend()
        session, _, _, reviewer = reliable(backend)
        session._context_length = 512
        result = session.send("Explain a lever.")
        self.assertEqual(backend.calls, [])
        self.assertEqual(result.attempted_models, ())
        self.assertEqual(result.attempts, ())
        self.assertEqual(reviewer.calls, [])
        self.assertIsNone(result.generation)

    def test_none_generates_general_answer_without_retrieval_and_retains_raw_route(self):
        route = semantic_route()
        backend = FakeBackend((chat_result("Recursion is a function calling itself."),))
        session, _, retriever, reviewer = reliable(backend, route=route)
        result = session.send("Explain recursion.")
        self.assertEqual(result.response.speech, "Recursion is a function calling itself.")
        self.assertEqual(retriever.retrieve_calls, [])
        self.assertEqual(result.effective_mode, "none")
        self.assertEqual(result.retrieval_status, "skipped")
        self.assertIs(result.route, route)
        self.assertIs(result.route.memory_required_generation, route.memory_required_generation)
        self.assertEqual(len(reviewer.calls), 1)
        self.assertEqual(len(result.attempts), 1)

    def test_optional_missing_irrelevant_or_unavailable_memory_still_answers(self):
        irrelevant = hybrid_match(memory(1, "Your camera is in the amber cabinet."))
        for records in ((), (irrelevant,), RuntimeError("retrieval unavailable")):
            with self.subTest(records=records):
                backend = FakeBackend((chat_result("Try soup with bread and a side salad."),))
                session, _, retriever, reviewer = reliable(
                    backend, route=semantic_route("optional", missing="personal preference"),
                    retriever=FakeRetriever(records),
                )
                result = session.send("Suggest a simple dinner.")
                self.assertEqual(result.response.speech, "Try soup with bread and a side salad.")
                self.assertEqual(result.effective_mode, "none")
                self.assertEqual(len(retriever.retrieve_calls), 1)
                self.assertEqual(reviewer.calls[0]["authorized_facts"], ())
                self.assertNotIn("amber", repr(backend.calls))
                self.assertEqual(result.response.memory_used, ())

    def test_required_missing_returns_application_question_without_generation(self):
        backend = FakeBackend()
        session, _, _, reviewer = reliable(
            backend, route=semantic_route("required", missing="personal schedule"),
        )
        result = session.send("When is my next appointment?")
        self.assertTrue(result.response.speech.startswith("I don't have that earlier information available. "))
        self.assertIn("time or date", result.response.speech)
        self.assertEqual(result.response.speech.count("?"), 1)
        self.assertIsNone(result.generation)
        self.assertEqual(result.attempts, ())
        self.assertEqual(backend.calls, [])
        self.assertEqual(reviewer.calls, [])
        self.assertEqual(result.generation_policy, "application_clarification")

    def test_optional_recall_preserves_explicit_general_fallback_without_saved_facts(self):
        request = ("What did I choose last time? If you do not have that saved, "
                   "suggest a general option.")
        answer = "Try folding a paper bookmark."
        route = semantic_route("optional")
        backend = FakeBackend((chat_result(answer),))
        session, _, retriever, reviewer = reliable(backend, route=route)

        result = session.send(request)

        self.assertIs(result.route, route)
        self.assertEqual(result.route.dependency.mode, "optional")
        self.assertTrue(result.route.decision.memory_required)
        self.assertEqual(result.effective_mode, "none")
        self.assertEqual(result.retrieval_status, "empty_or_irrelevant")
        self.assertEqual(result.response.speech, answer)
        self.assertEqual(result.response.memory_used, ())
        self.assertEqual(len(retriever.retrieve_calls), 1)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(result.attempted_models, (SMALL_MODEL,))
        self.assertEqual(len(reviewer.calls), 1)
        self.assertEqual(reviewer.calls[0]["authorized_facts"], ())

    def test_wrong_optional_route_cannot_deliver_personal_values_with_permissive_reviewer(self):
        route = semantic_route("optional")
        backend = FakeBackend((
            chat_result("Your favorite craft is pottery."),
            chat_result("Your favorite craft is knitting.", model=LARGE_MODEL),
        ))
        # This reviewer would pass either candidate. Independent checks must
        # quarantine both unsupported values before that verdict can help.
        reviewer = StubReviewer((("pass", "supported_answer"),) * 2)
        session, _, _, _ = reliable(backend, route=route, reviewer=reviewer)

        result = session.send("What is my favorite craft?")

        self.assertIs(result.route, route)
        self.assertEqual(result.route.dependency.mode, "optional")
        self.assertIsNone(result.generation)
        self.assertEqual(result.generation_policy, "application_clarification")
        self.assertEqual(result.attempted_models, (SMALL_MODEL, LARGE_MODEL))
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(len(result.attempts), 2)
        self.assertIn("unsupported_personal_claim", result.quality_issues)
        self.assertEqual(reviewer.calls, [])
        self.assertEqual(result.response.memory_used, ())
        self.assertNotIn("pottery", result.response.speech)
        self.assertNotIn("knitting", result.response.speech)
        self.assertEqual(session.messages[1:], ())

    def test_mixed_request_answers_only_standalone_general_fragment(self):
        fragment = "Explain how batteries work."
        query = "What time is my appointment? " + fragment
        backend = FakeBackend((chat_result("Batteries convert chemical energy into electrical energy."),))
        session, _, _, reviewer = reliable(backend, route=semantic_route(
            "required", missing="personal schedule", fragment=fragment,
        ))
        result = session.send(query)
        self.assertTrue(result.response.speech.startswith("I don't have that earlier information available. "))
        self.assertIn("What time is your appointment?", result.response.speech)
        self.assertEqual(result.response.speech.count("?"), 1)
        self.assertIn("chemical energy", result.response.speech)
        self.assertEqual(reviewer.calls[0]["request"], fragment)
        self.assertNotIn("appointment", backend.calls[0][1][-1].content)
        self.assertIsNotNone(result.generation)

        # With evidence available, both parts must be answered in one turn.
        item = memory(1, "Your camera is in the amber cabinet.")
        query = "Where is my camera? " + fragment
        general_speech = "Batteries convert chemical energy into electrical energy."
        speech = item.canonical_text + " " + general_speech
        raw_generation = chat_result(general_speech)
        backend = FakeBackend((raw_generation,))
        session, _, _, reviewer = reliable(
            backend, route=semantic_route("required", fragment=fragment),
            retriever=FakeRetriever((hybrid_match(item),)),
        )
        result = session.send(query)
        self.assertEqual(result.response.speech, speech)
        self.assertEqual(result.response.memory_used, (item.id,))
        self.assertEqual(reviewer.calls[0]["request"], query)
        self.assertEqual(reviewer.calls[0]["authorized_facts"], (item.canonical_text,))
        self.assertEqual(result.response_transform, "verified_mixed_prefix")
        self.assertIs(result.generation, raw_generation)
        self.assertEqual(json.loads(result.generation.content)["memory_used"], [])
        self.assertNotIn("amber", repr(backend.calls))
        self.assertNotIn("PERSONAL_MEMORY_DATA", repr(backend.calls))
        self.assertEqual(len(session._messages), 1)

    def test_mixed_answer_deleted_during_general_generation_never_discloses_prefix(self):
        item = memory(1, "Your camera is in the amber cabinet.")
        retriever = LifecycleRetriever((hybrid_match(item),))

        class DeletingBackend(FakeBackend):
            def chat(self, *args, **kwargs):
                generation = super().chat(*args, **kwargs)
                retriever.live = False
                return generation

        backend = DeletingBackend((chat_result("Batteries convert chemical energy into electrical energy."),))
        fragment = "Explain how batteries work."
        session, _, _, _ = reliable(
            backend, route=semantic_route("required", fragment=fragment), retriever=retriever,
        )
        result = session.send("Where is my camera? " + fragment)
        self.assertIsNone(result.generation)
        self.assertEqual(result.response.memory_used, ())
        self.assertNotIn("amber", result.response.speech)
        self.assertNotIn("amber", repr(backend.calls))
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(len(backend.calls), 1)

    def test_mixed_related_evidence_without_verified_renderer_asks_for_fact_and_answers_general(self):
        item = memory(1, "Noor is your workshop partner.")
        fragment = "Explain how batteries work."
        general = "Batteries convert chemical energy into electrical energy."
        backend = FakeBackend((chat_result(general),))
        session, _, _, reviewer = reliable(
            backend, route=semantic_route("required", fragment=fragment),
            retriever=FakeRetriever((hybrid_match(item),)),
        )
        result = session.send("Why did my workshop partner Noor move the camera? " + fragment)
        self.assertIsNotNone(result.generation)
        self.assertEqual(result.retrieval_status, "unverified_mixed_evidence")
        self.assertIn("I don't have that earlier information available.", result.response.speech)
        self.assertIn("Could you remind me", result.response.speech)
        self.assertIn(general, result.response.speech)
        self.assertNotIn("Noor", result.response.speech)
        self.assertEqual(result.response.memory_used, ())
        self.assertEqual(result.memory_diagnostics.supplied_ids, ())
        self.assertEqual(reviewer.calls[0]["request"], fragment)
        self.assertEqual(reviewer.calls[0]["authorized_facts"], ())
        self.assertNotIn("Noor", repr(backend.calls))

    def test_wrong_general_route_cannot_read_seeded_old_personal_values(self):
        for old in ("Your camera is in the amber cabinet.",
                    "Your camera was moved from the amber cabinet to the violet locker."):
            with self.subTest(old=old):
                backend = FakeBackend((chat_result("Try grouping similar items in labelled boxes."),))
                session, router, retriever, reviewer = reliable(backend)
                session._messages.extend((
                    ChatMessage("user", "Where is my camera?"), ChatMessage("assistant", old),
                ))
                result = session.send("Give me a general organizing tip.")
                self.assertEqual(result.response.memory_used, ())
                self.assertEqual(router.calls[0][1], ())
                self.assertEqual(retriever.retrieve_calls, [])
                self.assertNotIn("amber", repr(backend.calls))
                self.assertNotIn("violet", repr(backend.calls))
                self.assertEqual(reviewer.calls[0]["authorized_facts"], ())
                self.assertEqual(reviewer.calls[0]["history"], ())

    def test_rejected_named_disclosure_quarantines_followup_values_in_seeded_history(self):
        backend = FakeBackend((chat_result("Try grouping similar items in labelled boxes."),))
        session, router, _, reviewer = reliable(backend)
        session._messages.extend((
            ChatMessage("user", "Explain recursion."),
            ChatMessage("assistant", "Recursion is a function calling itself."),
            ChatMessage("user", "Noor lives in Kyoto."),
            ChatMessage("assistant", "Understood."),
            ChatMessage("user", "Summarize that."),
            ChatMessage("assistant", "Noor lives in Kyoto."),
        ))
        session.send("Give me an organizing tip.")
        self.assertEqual(router.calls[0][1], ())
        self.assertNotIn("Kyoto", repr(backend.calls))
        self.assertEqual(reviewer.calls[0]["history"], ())
        self.assertNotIn("Kyoto", repr(session._messages))

    def test_wrong_general_route_cannot_authorize_deleted_or_corrected_contact_fact(self):
        for current in ((), (hybrid_match(memory(2, "Noor lives in Osaka.")),)):
            with self.subTest(current=current):
                backend = FakeBackend((
                    chat_result("Noor lives in Kyoto."),
                    chat_result("I don't know where Noor lives. Could you provide current details?",
                                model=LARGE_MODEL),
                ))
                reviewer = StubReviewer((("retry", "unsupported_personal_claim"),
                                         ("pass", "supported_answer")))
                session, router, retriever, _ = reliable(
                    backend, reviewer=reviewer, retriever=FakeRetriever(current),
                )
                session._messages.extend((ChatMessage("user", "Where does Noor live?"),
                                          ChatMessage("assistant", "Noor lives in Kyoto.")))
                result = session.send("Where does Noor live?")
                self.assertEqual(router.calls[0][1], ())
                self.assertEqual(retriever.retrieve_calls, [])
                self.assertEqual(reviewer.calls[0]["authorized_facts"], ())
                self.assertEqual(reviewer.calls[0]["history"], ())
                self.assertNotIn("Kyoto", repr(backend.calls))
                self.assertNotIn("Osaka", repr(backend.calls))
                self.assertNotIn("Kyoto", result.response.speech)
                self.assertNotIn("Osaka", result.response.speech)
                self.assertEqual(len(session._messages), 1)

    def test_direct_personal_fact_grammar_blocks_forced_false_none_route(self):
        backend = FakeBackend()
        raw = semantic_route()
        session, _, retriever, _ = reliable(backend, route=raw)
        result = session.send("Where is my camera?")
        self.assertIs(result.route, raw)
        self.assertEqual(result.route.dependency.mode, "none")
        self.assertEqual(result.effective_mode, "required")
        self.assertIsNone(result.generation)
        self.assertEqual(len(retriever.retrieve_calls), 1)
        self.assertEqual(backend.calls, [])

    def test_current_assertions_reach_reviewer_but_question_assumptions_do_not(self):
        for query, speech, expected in (
            ("I have a headache. What should I do?",
             "You have a headache. Try resting and drinking water.", ("I have a headache",)),
            ("Why do I have a headache?",
             "There are many possible causes. Rest and drink water.", ()),
        ):
            with self.subTest(query=query):
                session, _, _, reviewer = reliable(FakeBackend((chat_result(speech),)))
                result = session.send(query)
                self.assertIsNotNone(result.generation)
                self.assertEqual(reviewer.calls[0]["authorized_facts"], expected)
                self.assertEqual(len(session._messages), 1)

    def test_matched_memory_is_verified_on_both_sides_of_answer_review(self):
        item = memory(1, "Your camera is in the amber cabinet.")
        retriever = LifecycleRetriever((hybrid_match(item),))
        reviewer = StubReviewer(callback=lambda: retriever.events.append("review"))
        session, _, _, _ = reliable(
            FakeBackend(), route=semantic_route("required"), retriever=retriever, reviewer=reviewer,
        )
        result = session.send("Where is my camera?")
        self.assertEqual(result.response.memory_used, (item.id,))
        self.assertEqual(reviewer.calls[0]["authorized_facts"], (item.canonical_text,))
        position = retriever.events.index("review")
        self.assertIn("snapshot", retriever.events[:position])
        self.assertIn("snapshot", retriever.events[position + 1:])
        self.assertEqual(len(session._messages), 1)

    def test_deletion_during_answer_review_quarantines_candidate(self):
        item = memory(1, "Your camera is in the amber cabinet.")
        retriever = LifecycleRetriever((hybrid_match(item),))
        reviewer = StubReviewer(callback=lambda: setattr(retriever, "live", False))
        backend = FakeBackend()
        session, _, _, _ = reliable(
            backend, route=semantic_route("required"), retriever=retriever, reviewer=reviewer,
        )
        result = session.send("Where is my camera?")
        self.assertIsNone(result.generation)
        self.assertNotIn("amber", result.response.speech)
        self.assertEqual(result.response.memory_used, ())
        self.assertEqual(len(reviewer.calls), 1)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(len(session._messages), 1)

    def test_optional_evidence_deleted_after_large_answer_falls_back_without_evidence(self):
        item = memory(1, "You prefer barley for workshop lunch.")
        retriever = LifecycleRetriever((hybrid_match(item),))
        reviewer = StubReviewer(callback=lambda: setattr(retriever, "live", False))
        backend = FakeBackend((
            chat_result(item.canonical_text, memory_used=(item.id,), model=LARGE_MODEL),
            chat_result("Try soup with bread and a side salad.", model=LARGE_MODEL),
        ))
        session, _, _, _ = reliable(
            backend, route=semantic_route("optional", missing="personal preference", size="large"),
            retriever=retriever, reviewer=reviewer,
        )
        result = session.send("Suggest a lunch for my workshop.")
        self.assertEqual(result.response.speech, "Try soup with bread and a side salad.")
        self.assertEqual(result.response.memory_used, ())
        self.assertEqual(result.effective_mode, "none")
        self.assertEqual(result.retrieval_status, "optional_evidence_discarded")
        self.assertEqual(result.attempted_models, (LARGE_MODEL, LARGE_MODEL))
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(len(reviewer.calls), 2)
        self.assertEqual(reviewer.calls[0]["authorized_facts"], (item.canonical_text,))
        self.assertEqual(reviewer.calls[1]["authorized_facts"], ())
        self.assertNotIn("barley", repr(backend.calls[1]))
        self.assertNotIn("PERSONAL_MEMORY_DATA", repr(backend.calls[1]))

    def test_optional_available_evidence_personalizes_only_from_relevant_record(self):
        preferred = memory(1, "You prefer barley for workshop lunch.")
        irrelevant = memory(2, "Your camera is in the amber cabinet.")
        speech = preferred.canonical_text + " Try a barley soup with bread."
        backend = FakeBackend((chat_result(speech, memory_used=(preferred.id,)),))
        session, _, _, reviewer = reliable(
            backend, route=semantic_route("optional", missing="personal preference"),
            retriever=FakeRetriever((hybrid_match(preferred), hybrid_match(irrelevant, 2))),
        )
        result = session.send("Suggest a lunch for my workshop.")
        self.assertEqual(result.response.speech, speech)
        self.assertEqual(result.effective_mode, "optional")
        self.assertEqual(result.response.memory_used, (preferred.id,))
        self.assertEqual(result.memory_diagnostics.retrieved_ids, (preferred.id, irrelevant.id))
        self.assertEqual(result.memory_diagnostics.supplied_ids, (preferred.id,))
        self.assertEqual(reviewer.calls[0]["authorized_facts"], (preferred.canonical_text,))
        self.assertNotIn("amber", repr(backend.calls))

    def test_personal_turns_never_enter_reusable_history_for_any_mode(self):
        for mode, query, speech, records in (
            ("none", "I live in Kyoto.", "Thanks for telling me.", ()),
            ("optional", "Can you suggest a meal for my dinner?", "Try soup and bread.", ()),
            ("required", "Where is my camera?", "Your camera is in the amber cabinet.",
             (hybrid_match(memory(1, "Your camera is in the amber cabinet.")),)),
        ):
            with self.subTest(mode=mode):
                backend = FakeBackend() if records else FakeBackend((chat_result(speech),))
                session, _, _, _ = reliable(backend, route=semantic_route(mode),
                                            retriever=FakeRetriever(records))
                session.send(query)
                self.assertEqual(len(session._messages), 1)

    def test_general_and_draft_followups_preserve_safe_task_context(self):
        for first, first_reply, followup, second_reply in (
            ("Explain recursion.", "Recursion is a function calling itself.",
             "Give an example.", "Factorial is the product of a number and the preceding factorial."),
            ("Write a first-person story about a pilot.", "I am a pilot living on a floating island.",
             "Make it shorter.", "I fly above a floating island."),
        ):
            with self.subTest(first=first):
                backend = FakeBackend((chat_result(first_reply), chat_result(second_reply),
                                       chat_result("I love flying above this friendly island.")))
                session, router, _, reviewer = reliable(backend)
                session.send(first)
                result = session.send(followup)
                self.assertIsNotNone(result.generation)
                self.assertEqual([message.content for message in router.calls[1][1]],
                                 [first, first_reply])
                self.assertIn(first_reply, [message.content for message in backend.calls[1][1]])
                self.assertEqual(len(session._messages), 5)
                if "story" in first:
                    self.assertTrue(reviewer.calls[1]["drafting"])
                    session.send("Make it warmer.")
                    self.assertEqual(len(router.calls[2][1]), 4)
                    self.assertTrue(reviewer.calls[2]["drafting"])
                    self.assertEqual(len(session._messages), 7)

    def test_comparison_context_survives_into_router_generator_and_answer_review(self):
        first = "Distinguish a thermometer from a thermostat."
        explanation = ("A thermometer measures temperature. A thermostat controls heating "
                       "to maintain a set temperature.")
        followup = "Give a household example of each."
        example = ("A kitchen thermometer measures soup temperature. A wall thermostat "
                   "switches home heating on and off.")
        backend = FakeBackend((chat_result(explanation), chat_result(example)))
        session, router, _, reviewer = reliable(backend)

        session.send(first)
        result = session.send(followup)

        self.assertEqual(result.response.speech, example)
        self.assertEqual([message.content for message in router.calls[1][1]], [first, explanation])
        self.assertIn(explanation, [message.content for message in backend.calls[1][1]])
        self.assertEqual([message.content for message in reviewer.calls[1]["history"]],
                         [first, explanation])
        self.assertEqual(len(session.messages), 5)

    def test_private_comparison_in_seeded_history_stays_quarantined(self):
        backend = FakeBackend((chat_result("Recursion is a function calling itself."),))
        session, router, _, reviewer = reliable(backend)
        session._messages.extend((
            ChatMessage("user", "Differentiate Noor's preferences from Leila's."),
            ChatMessage("assistant", "Noor enjoys painting and Leila enjoys pottery."),
        ))

        session.send("Explain recursion.")

        self.assertEqual(router.calls[0][1], ())
        self.assertEqual(reviewer.calls[0]["history"], ())
        self.assertNotIn("Noor", repr(backend.calls))
        self.assertNotIn("pottery", repr(session.messages))

    def test_optional_scaffolding_is_quarantined_before_one_concrete_retry(self):
        cases = (
            ("I am choosing an escape-room theme. You can use any interests you know for me; "
             "otherwise pick a broadly appealing theme.",
             "I'm choosing an escape-room theme. Let's plan a fun and engaging experience for you.",
             "Choose a lost-library mystery with coded book titles and a hidden key."),
            ("Recommend a short audio drama. Knowing my tastes could help, but choose a "
             "beginner-friendly one if you lack them.",
             "I don't have personal preferences, but I can recommend a short audio drama. "
             "Let me know if you're looking for something beginner-friendly.",
             "Try The Hitchhiker's Guide to the Galaxy, starting with the first radio episode."),
        )
        for request, bad, good in cases:
            with self.subTest(request=request):
                backend = FakeBackend((chat_result(bad), chat_result(good, model=LARGE_MODEL)))
                session, _, _, reviewer = reliable(backend, route=semantic_route("optional"))

                result = session.send(request)

                self.assertEqual(result.response.speech, good)
                self.assertEqual(result.effective_mode, "none")
                self.assertEqual(result.attempted_models, (SMALL_MODEL, LARGE_MODEL))
                self.assertEqual(len(result.attempts), 2)
                self.assertIn("promise_only", result.quality_issues)
                self.assertEqual([call["answer"] for call in reviewer.calls], [good])
                self.assertNotIn(bad, repr(session.messages))

    def test_repetitive_or_vacuous_small_reply_gets_only_one_large_retry(self):
        for bad in (chat_result("I can only plan and plan. I can only plan and plan."),
                    chat_result("Sure, I can help with that. Let me know what you need."),
                    chat_result("I cannot help with that task, but try breaking it into smaller steps."),
                    chat_result(raw="{invalid json")):
            with self.subTest(bad=bad):
                backend = FakeBackend((bad, chat_result(
                    "Recursion is a function calling itself until a stopping condition.", model=LARGE_MODEL,
                )))
                session, _, _, reviewer = reliable(backend)
                result = session.send("Explain recursion.")
                self.assertEqual([call[0] for call in backend.calls], [SMALL_MODEL, LARGE_MODEL])
                self.assertEqual(len(result.attempts), 2)
                self.assertEqual(len(reviewer.calls), 1)
                self.assertEqual(result.generation.model, LARGE_MODEL)
                self.assertEqual(result.fallback_from_model, SMALL_MODEL)

    def test_invalid_review_raw_is_preserved_and_unchecked_answer_is_retried(self):
        invalid = chat_result(raw="{malformed verdict", model=LARGE_MODEL)
        valid = chat_result(raw='{"verdict":"pass","reason":"supported_answer"}', model=LARGE_MODEL)
        reviewer = AnswerReviewer(ReviewBackend((invalid, valid)), model=LARGE_MODEL)
        first = chat_result("A battery stores chemical energy.")
        second = chat_result("Batteries convert chemical energy into electrical energy.", model=LARGE_MODEL)
        session, _, _, _ = reliable(FakeBackend((first, second)), reviewer=reviewer)
        result = session.send("Explain how batteries work.")
        self.assertIs(result.generation, second)
        self.assertEqual(result.attempts, (first, second))
        self.assertEqual(result.review_attempts, (invalid, valid))
        self.assertEqual(len(result.answer_reviews), 1)
        self.assertIs(result.answer_reviews[0].generation, valid)
        self.assertIn("RoutingError", result.quality_issues)
        self.assertNotIn("malformed", result.response.speech)

    def test_robot_specs_must_be_supported_by_deployment_facts(self):
        facts = ("This application uses local speech recognition and returns terminal text.",)
        backend = FakeBackend((
            chat_result("I have 8 GB RAM and an 8-core processor."),
            chat_result(facts[0] + " I do not have verified RAM or processor details.", model=LARGE_MODEL),
        ))
        reviewer = StubReviewer((("retry", "unhelpful_answer"), ("pass", "supported_answer")))
        session, _, _, _ = reliable(backend, reviewer=reviewer, runtime_facts=facts)
        result = session.send("What are your specifications, robot?")
        self.assertEqual(result.generation.model, LARGE_MODEL)
        self.assertNotIn("8 GB", result.response.speech)
        self.assertIn("do not have verified RAM", result.response.speech)
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual([call["deployment_facts"] for call in reviewer.calls], [facts, facts])
        self.assertEqual([call["authorized_facts"] for call in reviewer.calls], [(), ()])

    def test_generator_deployment_context_is_relevant_but_review_facts_are_unconditional(self):
        facts = deployment_facts(load_config())
        for request, answer, relevant in (
            ("Suggest a way to organize documents.", "Group related documents into labelled folders.", False),
            ("Who are you?", "This is the offline Oline HRI assistant.", True),
            ("What are your specifications, robot?", facts[-1], True),
            ("How can I use Whisper?", "Use Whisper to transcribe a speech recording.", True),
        ):
            with self.subTest(request=request):
                backend = FakeBackend((chat_result(answer),))
                review_backend = ReviewBackend((chat_result(
                    raw='{"verdict":"pass","reason":"supported_answer"}', model=LARGE_MODEL,
                ),))
                reviewer = AnswerReviewer(review_backend, model=LARGE_MODEL)
                session, _, _, _ = reliable(backend, runtime_facts=facts, reviewer=reviewer)

                result = session.send(request)

                self.assertEqual(result.response.speech, answer)
                prompt = "\n".join(message.content for message in backend.calls[0][1])
                for fact in facts:
                    self.assertEqual(fact in prompt, relevant)
                envelope = json.loads(review_backend.calls[0][1][-1].content)
                self.assertEqual(envelope["deployment_facts"], list(facts))
                self.assertEqual(result.attempted_models, (SMALL_MODEL,))

    def test_unsolicited_internal_tool_guidance_uses_existing_retry_bound(self):
        facts = deployment_facts(load_config())
        bad = "Sort items into labelled groups. Use your local Whisper and Silero VAD for this."
        good = "Sort items by purpose, label the groups, and put each group in one place."
        for second in (good, bad):
            with self.subTest(second=second):
                backend = FakeBackend((chat_result(bad), chat_result(second, model=LARGE_MODEL)))
                session, _, _, reviewer = reliable(backend, runtime_facts=facts)

                result = session.send("Suggest a simple way to organize things.")

                self.assertEqual(result.attempted_models, (SMALL_MODEL, LARGE_MODEL))
                self.assertEqual(len(result.attempts), 2)
                self.assertIn("unsolicited_internal_tool_guidance", result.quality_issues)
                self.assertNotIn("Whisper", result.response.speech)
                self.assertNotIn(bad, repr(session.messages))
                if second == good:
                    self.assertEqual(result.response.speech, good)
                    self.assertEqual([call["answer"] for call in reviewer.calls], [good])
                    self.assertEqual(reviewer.calls[0]["deployment_facts"], facts)
                else:
                    self.assertIsNone(result.generation)
                    self.assertEqual(reviewer.calls, [])

    def test_second_bad_reply_stops_at_two_and_returns_application_clarification(self):
        bad = "Sure, I can help. Let me know what you need."
        backend = FakeBackend((chat_result(bad), chat_result(bad, model=LARGE_MODEL)))
        session, _, _, reviewer = reliable(backend)
        result = session.send("Explain recursion.")
        self.assertIsNone(result.generation)
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(reviewer.calls, [])
        self.assertNotEqual(result.response.speech, bad)
        self.assertEqual(result.effective_mode, "clarify")

    def test_independent_reviewer_can_reject_unsupported_claim_on_any_general_route(self):
        for mode in ("none", "optional"):
            with self.subTest(mode=mode):
                backend = FakeBackend((chat_result("The amber cabinet is the one."),
                                       chat_result("The amber cupboard is the one.", model=LARGE_MODEL)))
                reviewer = StubReviewer((
                    ("retry", "unsupported_personal_claim"), ("retry", "unsupported_personal_claim"),
                ))
                session, _, _, _ = reliable(backend, route=semantic_route(mode), reviewer=reviewer)
                result = session.send("Suggest an organizing approach.")
                self.assertIsNone(result.generation)
                self.assertNotIn("amber", result.response.speech)
                self.assertEqual(len(reviewer.calls), 2)
                self.assertIn("unsupported_personal_claim", result.quality_issues)

    def test_unresolved_request_needs_clarification_without_generation(self):
        backend = FakeBackend()
        session, _, retriever, reviewer = reliable(backend, route=semantic_route("clarify"))
        result = session.send("It's like a... it's like a...")
        self.assertIsNone(result.generation)
        self.assertEqual(result.effective_mode, "clarify")
        self.assertEqual(backend.calls, [])
        self.assertEqual(retriever.retrieve_calls, [])
        self.assertEqual(reviewer.calls, [])


if __name__ == "__main__":
    unittest.main()
