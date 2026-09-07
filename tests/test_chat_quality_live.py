"""Opt-in live regressions for routing and memory-grounded answer quality."""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
import unittest

from oline_hri.config import load_config
from oline_hri.conversation import Conversation
from oline_hri.embedding import BgeOnnxEmbedder
from oline_hri.memory import MemoryStore
from oline_hri.ollama import ChatResult, OllamaClient
from oline_hri.retrieval import HybridRetriever
from oline_hri.routing import (
    ConversationRouter,
    RouteDecision,
    RoutingResult,
)


RUN_LIVE = os.environ.get("OLINE_HRI_RUN_LIVE_QUALITY") == "1"

PARTNER_MEMORY_ID = "mem_000000000000000000000000000000a1"
MEETING_MEMORY_ID = "mem_000000000000000000000000000000a2"
FORMAT_MEMORY_ID = "mem_000000000000000000000000000000a3"
ALL_MEMORY_IDS = frozenset(
    {PARTNER_MEMORY_ID, MEETING_MEMORY_ID, FORMAT_MEMORY_ID}
)

ARCHITECTURE_PROMPT = (
    "Compare three offline robot architectures, reason through their "
    "tradeoffs, and create a detailed deployment plan."
)
COMPLEX_PLAN_PROMPT = (
    "Using what you remember about Theo, my robotics-project meeting schedule, "
    "and my preferred project-plan format, create a plan for our next meeting."
)

_CLOCK_TIME_PATTERN = re.compile(
    r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d"
    r"(?:\s*(?:a\.?m\.?|p\.?m\.?))?\b|"
    r"\b(?:0?[1-9]|1[0-2])\s*(?:a\.?m\.?|p\.?m\.?)\b",
    re.IGNORECASE,
)
_SPELLED_CLOCK_TIME_PATTERN = re.compile(
    r"\b(?:at|around|by|from|until|before|after)\s+"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"(?:\s+thirty)?"
    r"(?:\s+(?:o['’]?clock|in the morning|a\.?m\.?|p\.?m\.?))?\b|"
    r"\b(?:at|around|by|from|until|before|after)\s+"
    r"(?:noon|midday|midnight)\b",
    re.IGNORECASE,
)
_RELATIVE_CLOCK_TIME_PATTERN = re.compile(
    r"\b(?:half|quarter)\s+(?:past|to)\s+"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
    re.IGNORECASE,
)
_CONTEXTUAL_CLOCK_TIME_PATTERN = re.compile(
    r"\b(?:at|around|by|from|until|before|after)\s+"
    r"(?:0?[1-9]|1[0-2])\b",
    re.IGNORECASE,
)
_CALENDAR_DATE_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\b(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|"
    r"mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?))"
    r"(?:,?\s+\d{4})?\b|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|"
    r"\b(?:the|on)\s+\d{1,2}(?:st|nd|rd|th)\b",
    re.IGNORECASE,
)
_RELATIVE_TUESDAY_PATTERN = re.compile(
    r"\b(?:this|next|coming|upcoming)\s+tuesday\b",
    re.IGNORECASE,
)
_UNSUPPORTED_DAYPART_PATTERN = re.compile(
    r"\b(?:afternoons?|evenings?|nights?|noon|midday|midnight)\b|"
    r"\b(?:early|late)\s+(?:tuesday\s+)?mornings?\b|"
    r"\b(?:early|late)\s+tuesday\b",
    re.IGNORECASE,
)
_UNSUPPORTED_PERSON_NAME_PATTERN = re.compile(
    r"\b(?:Alex|Jordan|Mira|Sam|Taylor)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_RELATIONSHIP_PATTERN = re.compile(
    r"\b(?:client|colleague|coworker|friend|manager|relative|sibling|spouse)\b",
    re.IGNORECASE,
)
_REFUSAL_PATTERN = re.compile(
    r"\b(?:i (?:cannot|can't|am unable to)\s+"
    r"(?:answer|help|provide|compare|analy[sz]e|recommend|create)|"
    r"i (?:will not|won't|must refuse)|"
    r"unable to (?:answer|help|provide|compare|analy[sz]e)|"
    r"cannot (?:answer|help|provide|compare|analy[sz]e|recommend|create))\b",
    re.IGNORECASE,
)
_PHYSICAL_DEFLECTION_PATTERN = re.compile(
    r"\bi (?:cannot|can't|do not|don't|am unable)"
    r"[\s\S]{0,80}\bphysical actions?\b|"
    r"\bi (?:do not|don't) have[\s\S]{0,80}"
    r"\b(?:access|ability|capability)\b",
    re.IGNORECASE,
)
_WRONG_PERSPECTIVE_PATTERN = re.compile(
    r"\b(?:the )?user(?:'s)?\b|"
    r"\bi (?:usually )?(?:prefer|like|want)\b|"
    r"\btuesday mornings? (?:work|suit)s? for me\b|"
    r"\bmy (?:robotics |project )?(?:project )?partner\b|"
    r"\bmy (?:meeting preference|preferred (?:meeting )?time)\b",
    re.IGNORECASE,
)
_PARTNER_PERSPECTIVE_PATTERN = re.compile(
    r"\byour (?:fictional )?robotics project partner\b|"
    r"\byour partner (?:on|for) the robotics project\b",
    re.IGNORECASE,
)
_NEGATED_PARTNER_PATTERN = re.compile(
    r"\bTheo\b[^.!?]{0,80}\b(?:is not|isn't|was not|wasn't)\b"
    r"[^.!?]{0,80}\b(?:partner|robotics project)\b|"
    r"\bTheo\b[^.!?]{0,80}\bnot\b[^.!?]{0,40}"
    r"\b(?:partner|robotics project)\b",
    re.IGNORECASE,
)
_NEGATED_MEETING_PATTERN = re.compile(
    r"\b(?:not|never|don't|doesn't|isn't|aren't)\b"
    r"[^.!?]{0,50}\btuesday mornings?\b|"
    r"\btuesday mornings?\b[^.!?]{0,50}"
    r"\b(?:not|never|don't|doesn't|isn't|aren't)\b",
    re.IGNORECASE,
)
_OTHER_WEEKDAY_PATTERN = re.compile(
    r"\b(?:monday|wednesday|thursday|friday|saturday|sunday)s?\b",
    re.IGNORECASE,
)
_PLAN_ACTION_PATTERN = re.compile(
    r"\b(?:ask|assign|bring|confirm|coordinate|decide|discuss|draft|"
    r"finali[sz]e|gather|identify|meet|outline|plan|prepare|review|"
    r"schedule|send|set|share)\w*\b",
    re.IGNORECASE,
)


class _SeededBackend:
    """Use deterministic generation while preserving router overrides."""

    def __init__(self, delegate: OllamaClient, *, temperature: float) -> None:
        self._delegate = delegate
        self._temperature = temperature

    def chat(
        self,
        model,
        messages,
        *,
        response_format=None,
        temperature=None,
        seed=None,
    ):
        return self._delegate.chat(
            model,
            messages,
            response_format=response_format,
            temperature=self._temperature if temperature is None else temperature,
            seed=42 if seed is None else seed,
        )


class _FixedRouter:
    """Bypass known routing defects so generation failures remain visible."""

    def __init__(self, decision: RouteDecision, *, model: str) -> None:
        self._result = RoutingResult(
            decision=decision,
            memory_required_generation=ChatResult(
                model=model,
                content=(
                    '{"memory_required":'
                    + ("true" if decision.memory_required else "false")
                    + "}"
                ),
                done_reason="stop",
                total_duration_ns=0,
                load_duration_ns=0,
                prompt_eval_count=0,
                eval_count=0,
                eval_duration_ns=0,
            ),
            model_size_generation=ChatResult(
                model=model,
                content='{"model_size":"' + decision.model_size + '"}',
                done_reason="stop",
                total_duration_ns=0,
                load_duration_ns=0,
                prompt_eval_count=0,
                eval_count=0,
                eval_duration_ns=0,
            ),
        )

    def route(self, user_text, *, history=()):
        return self._result


@unittest.skipUnless(
    RUN_LIVE,
    "set OLINE_HRI_RUN_LIVE_QUALITY=1 to run slow local quality regressions",
)
class LiveChatQualityRegressionTests(unittest.TestCase):
    """Exercise the exact synthetic memories without touching the live DB."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config()
        cls._temporary_directory = tempfile.TemporaryDirectory(
            prefix="oline-hri-live-quality-"
        )
        try:
            database_path = (
                Path(cls._temporary_directory.name) / "memory.sqlite3"
            )
            configured_path = Path(
                cls.config.memory.database_path
            ).expanduser()
            if database_path.resolve() == configured_path.resolve():
                raise AssertionError(
                    "live regression database must be isolated from configured memory"
                )

            memory_ids = iter(
                (PARTNER_MEMORY_ID, MEETING_MEMORY_ID, FORMAT_MEMORY_ID)
            )
            embedder = BgeOnnxEmbedder(
                cls.config.embedding.model_directory,
                cls.config.embedding.intra_op_threads,
            )
            cls.store = MemoryStore(
                database_path,
                profile_id="fictional_live_quality_v1",
                embedder=embedder,
                memory_id_factory=lambda: next(memory_ids),
            )
            partner = cls.store.remember(
                "Theo is the user's fictional robotics project partner.",
                kind="relationship",
            )
            meeting = cls.store.remember(
                "The user prefers robotics project meetings on Tuesday mornings.",
                kind="routine",
            )
            plan_format = cls.store.remember(
                "The user prefers project plans containing exactly three "
                "concise steps.",
                kind="preference",
            )
            if (
                partner.id,
                meeting.id,
                plan_format.id,
            ) != (
                PARTNER_MEMORY_ID,
                MEETING_MEMORY_ID,
                FORMAT_MEMORY_ID,
            ):
                raise AssertionError("fictional live memory IDs are not deterministic")

            cls.client = OllamaClient(
                cls.config.ollama, cls.config.generation
            )
            cls.backend = _SeededBackend(
                cls.client,
                temperature=cls.config.generation.temperature,
            )
        except BaseException:
            cls._temporary_directory.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def conversation(
        self,
        decision: RouteDecision,
        *,
        context_length: int | None = None,
    ) -> Conversation:
        return Conversation(
            self.backend,
            system_prompt=self.config.conversation.system_prompt,
            router=_FixedRouter(
                decision, model=self.config.ollama.small_model
            ),
            retriever=HybridRetriever(self.store),
            small_model=self.config.ollama.small_model,
            large_model=self.config.ollama.large_model,
            context_length=(
                self.config.generation.context_length
                if context_length is None
                else context_length
            ),
            max_output_tokens=self.config.generation.max_output_tokens,
        )

    def real_routed_conversation(self) -> Conversation:
        """Build an isolated conversation using the production router."""

        return Conversation(
            self.backend,
            system_prompt=self.config.conversation.system_prompt,
            router=ConversationRouter(
                self.backend, model=self.config.ollama.small_model
            ),
            retriever=HybridRetriever(self.store),
            small_model=self.config.ollama.small_model,
            large_model=self.config.ollama.large_model,
            context_length=self.config.generation.context_length,
            max_output_tokens=self.config.generation.max_output_tokens,
        )

    def assert_route_and_model(
        self, reply, expected_route: RouteDecision, expected_model: str
    ) -> None:
        self.assertIsNotNone(reply.route)
        self.assertEqual(reply.route.decision, expected_route)
        self.assertEqual(reply.generation.model, expected_model)

    def assert_user_perspective(self, speech: str) -> None:
        self.assertNotRegex(speech, _WRONG_PERSPECTIVE_PATTERN)

    def assert_no_invented_time_or_date(self, speech: str) -> None:
        self.assertNotRegex(speech, _CLOCK_TIME_PATTERN)
        self.assertNotRegex(speech, _SPELLED_CLOCK_TIME_PATTERN)
        self.assertNotRegex(speech, _RELATIVE_CLOCK_TIME_PATTERN)
        self.assertNotRegex(speech, _CONTEXTUAL_CLOCK_TIME_PATTERN)
        self.assertNotRegex(speech, _CALENDAR_DATE_PATTERN)
        self.assertNotRegex(speech, _OTHER_WEEKDAY_PATTERN)
        self.assertNotRegex(speech, _RELATIVE_TUESDAY_PATTERN)
        self.assertNotRegex(speech, _UNSUPPORTED_DAYPART_PATTERN)

    def assert_architecture_answer(self, speech: str) -> None:
        self.assertNotRegex(speech, _REFUSAL_PATTERN)
        self.assertNotRegex(speech, _PHYSICAL_DEFLECTION_PATTERN)
        tradeoff_terms = (
            "adapt",
            "bandwidth",
            "complex",
            "coordina",
            "cost",
            "failure",
            "fault",
            "flexib",
            "isolat",
            "latency",
            "maintain",
            "memory",
            "overhead",
            "power",
            "predict",
            "reliab",
            "resource",
            "safety",
            "scal",
            "security",
        )
        self.assertGreaterEqual(
            sum(term in speech.casefold() for term in tradeoff_terms),
            3,
            speech,
        )
        self.assertRegex(
            speech,
            re.compile(r"\b(?:but|however|whereas|while)\b|trade-?offs?", re.I),
        )
        self.assertRegex(
            speech,
            re.compile(r"\b(?:recommend|best fit|choose)\w*\b", re.I),
        )
        plan_actions = re.findall(
            r"\b(?:define|deploy|implement|integrate|monitor|select|test|"
            r"validate|verify)\w*\b",
            speech,
            re.IGNORECASE,
        )
        self.assertGreaterEqual(len(plan_actions), 2, speech)

    def assert_three_concise_plan_steps(self, speech: str) -> None:
        marker_patterns = (
            re.compile(
                r"(?:^|\s)(?:step\s+)?([1-9])(?:[.)]|\s*:)\s+",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:^|\s)(first|second|third|finally|lastly)"
                r"\s*[,.:]\s+",
                re.IGNORECASE,
            ),
        )
        markers = list(marker_patterns[0].finditer(speech))
        if markers:
            self.assertEqual(
                [int(marker.group(1)) for marker in markers],
                [1, 2, 3],
                speech,
            )
        else:
            markers = list(marker_patterns[1].finditer(speech))
            if markers:
                labels = [marker.group(1).casefold() for marker in markers]
                self.assertEqual(len(labels), 3, speech)
                self.assertEqual(labels[:2], ["first", "second"], speech)
                self.assertIn(
                    labels[2], {"third", "finally", "lastly"}, speech
                )

        if markers:
            steps = []
            for index, marker in enumerate(markers):
                end = (
                    markers[index + 1].start()
                    if index + 1 < len(markers)
                    else len(speech)
                )
                steps.append(speech[marker.end() : end].strip())
        else:
            steps = [
                re.sub(r"^\s*[-*•]\s+", "", line).strip()
                for line in speech.splitlines()
                if re.match(r"^\s*[-*•]\s+", line)
            ]
            self.assertEqual(len(steps), 3, speech)

        self.assertEqual(len(steps), 3, speech)
        self.assertTrue(all(steps), speech)
        for step in steps:
            self.assertLessEqual(len(step), 200, speech)
            self.assertRegex(step, _PLAN_ACTION_PATTERN, speech)

    def test_large_general_architecture_is_answered_without_refusal(
        self,
    ) -> None:
        reply = self.conversation(
            RouteDecision(False, "large")
        ).send(ARCHITECTURE_PROMPT)

        self.assert_route_and_model(
            reply,
            RouteDecision(False, "large"),
            self.config.ollama.large_model,
        )
        self.assertEqual(
            reply.memory_diagnostics.to_dict(),
            {
                "retrieved_ids": [],
                "supplied_ids": [],
                "model_used_ids": [],
            },
        )
        speech = reply.response.speech
        self.assert_architecture_answer(speech)

    def test_theo_recall_is_small_grounded_and_uses_user_perspective(
        self,
    ) -> None:
        prompts = ("Who is Theo to me?", "How do I know Theo?")
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                reply = self.conversation(
                    RouteDecision(True, "small")
                ).send(prompt)

                self.assert_route_and_model(
                    reply,
                    RouteDecision(True, "small"),
                    self.config.ollama.small_model,
                )
                self.assertIn(
                    PARTNER_MEMORY_ID,
                    reply.memory_diagnostics.retrieved_ids,
                )
                self.assertIn(
                    PARTNER_MEMORY_ID,
                    reply.memory_diagnostics.supplied_ids,
                )
                self.assertEqual(
                    reply.memory_diagnostics.model_used_ids,
                    (PARTNER_MEMORY_ID,),
                )
                speech = reply.response.speech
                self.assertRegex(speech, re.compile(r"\bTheo\b", re.I))
                self.assertRegex(speech, _PARTNER_PERSPECTIVE_PATTERN)
                self.assertNotRegex(speech, _NEGATED_PARTNER_PATTERN)
                self.assertNotRegex(speech, _REFUSAL_PATTERN)
                self.assertNotRegex(speech, _PHYSICAL_DEFLECTION_PATTERN)
                self.assertNotRegex(speech, _UNSUPPORTED_PERSON_NAME_PATTERN)
                self.assertNotRegex(speech, _UNSUPPORTED_RELATIONSHIP_PATTERN)
                self.assert_user_perspective(speech)

    def test_meeting_recall_preserves_tuesday_mornings_without_precision(
        self,
    ) -> None:
        prompts = (
            "What is my preferred meeting time for the robotics project?",
            "When do I usually want robotics project meetings?",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                reply = self.conversation(
                    RouteDecision(True, "small")
                ).send(prompt)

                self.assert_route_and_model(
                    reply,
                    RouteDecision(True, "small"),
                    self.config.ollama.small_model,
                )
                self.assertIn(
                    MEETING_MEMORY_ID,
                    reply.memory_diagnostics.retrieved_ids,
                )
                self.assertIn(
                    MEETING_MEMORY_ID,
                    reply.memory_diagnostics.supplied_ids,
                )
                self.assertEqual(
                    reply.memory_diagnostics.model_used_ids,
                    (MEETING_MEMORY_ID,),
                )
                speech = reply.response.speech
                self.assertRegex(
                    speech,
                    re.compile(r"\btuesday mornings?\b", re.IGNORECASE),
                )
                self.assertNotRegex(speech, _NEGATED_MEETING_PATTERN)
                self.assertRegex(
                    speech,
                    re.compile(r"\b(?:you|your)\b", re.IGNORECASE),
                )
                self.assert_no_invented_time_or_date(speech)
                self.assertNotRegex(speech, _REFUSAL_PATTERN)
                self.assertNotRegex(speech, _PHYSICAL_DEFLECTION_PATTERN)
                self.assertNotRegex(speech, re.compile(r"\bTheo\b", re.I))
                self.assertNotRegex(speech, _UNSUPPORTED_PERSON_NAME_PATTERN)
                self.assertNotRegex(speech, _UNSUPPORTED_RELATIONSHIP_PATTERN)
                self.assert_user_perspective(speech)

    def test_meeting_recall_uses_user_perspective(self) -> None:
        reply = self.conversation(RouteDecision(True, "small")).send(
            "What is my preferred meeting time for the robotics project?"
        )

        self.assert_route_and_model(
            reply,
            RouteDecision(True, "small"),
            self.config.ollama.small_model,
        )
        self.assertIn(
            MEETING_MEMORY_ID,
            reply.memory_diagnostics.retrieved_ids,
        )
        self.assertIn(
            MEETING_MEMORY_ID,
            reply.memory_diagnostics.supplied_ids,
        )
        self.assertEqual(
            reply.memory_diagnostics.model_used_ids,
            (MEETING_MEMORY_ID,),
        )
        speech = reply.response.speech
        self.assertRegex(
            speech,
            re.compile(r"\btuesday mornings?\b", re.IGNORECASE),
        )
        self.assertRegex(
            speech,
            re.compile(r"\b(?:you|your)\b", re.IGNORECASE),
        )
        self.assertNotRegex(speech, _NEGATED_MEETING_PATTERN)
        self.assertNotRegex(speech, _REFUSAL_PATTERN)
        self.assertNotRegex(speech, _PHYSICAL_DEFLECTION_PATTERN)
        self.assert_user_perspective(speech)

    def test_complex_theo_meeting_plan_uses_every_memory_in_three_steps(
        self,
    ) -> None:
        reply = self.conversation(RouteDecision(True, "large")).send(
            COMPLEX_PLAN_PROMPT
        )

        self.assert_route_and_model(
            reply,
            RouteDecision(True, "large"),
            self.config.ollama.large_model,
        )
        self.assertEqual(
            set(reply.memory_diagnostics.retrieved_ids), ALL_MEMORY_IDS
        )
        self.assertEqual(
            set(reply.memory_diagnostics.supplied_ids), ALL_MEMORY_IDS
        )
        self.assertEqual(
            set(reply.memory_diagnostics.model_used_ids), ALL_MEMORY_IDS
        )

        speech = reply.response.speech
        self.assert_three_concise_plan_steps(speech)
        self.assertRegex(speech, re.compile(r"\bTheo\b", re.I))
        self.assertNotRegex(speech, _NEGATED_PARTNER_PATTERN)
        self.assertRegex(
            speech, re.compile(r"\btuesday mornings?\b", re.IGNORECASE)
        )
        self.assertNotRegex(speech, _NEGATED_MEETING_PATTERN)
        self.assert_no_invented_time_or_date(speech)
        self.assertNotRegex(speech, _REFUSAL_PATTERN)
        self.assertNotRegex(speech, _PHYSICAL_DEFLECTION_PATTERN)
        self.assert_user_perspective(speech)

    def test_exact_failed_greeting_then_architecture_end_to_end(self) -> None:
        conversation = self.real_routed_conversation()

        greeting = conversation.send("Hello there!")
        self.assert_route_and_model(
            greeting,
            RouteDecision(False, "small"),
            self.config.ollama.small_model,
        )
        self.assertEqual(greeting.memory_diagnostics.to_dict(), {
            "retrieved_ids": [],
            "supplied_ids": [],
            "model_used_ids": [],
        })

        reply = conversation.send(ARCHITECTURE_PROMPT)

        self.assert_route_and_model(
            reply,
            RouteDecision(False, "large"),
            self.config.ollama.large_model,
        )
        self.assertEqual(reply.memory_diagnostics.to_dict(), {
            "retrieved_ids": [],
            "supplied_ids": [],
            "model_used_ids": [],
        })
        self.assert_architecture_answer(reply.response.speech)

    def test_exact_failed_theo_recall_end_to_end(self) -> None:
        reply = self.real_routed_conversation().send("Who is Theo to me?")

        self.assert_route_and_model(
            reply,
            RouteDecision(True, "small"),
            self.config.ollama.small_model,
        )
        self.assertEqual(
            reply.memory_diagnostics.model_used_ids,
            (PARTNER_MEMORY_ID,),
        )
        self.assertIn(
            PARTNER_MEMORY_ID, reply.memory_diagnostics.retrieved_ids
        )
        self.assertEqual(
            reply.memory_diagnostics.supplied_ids, (PARTNER_MEMORY_ID,)
        )
        speech = reply.response.speech
        self.assertRegex(speech, re.compile(r"\bTheo\b", re.IGNORECASE))
        self.assertRegex(speech, _PARTNER_PERSPECTIVE_PATTERN)
        self.assertNotRegex(speech, _NEGATED_PARTNER_PATTERN)
        self.assertNotRegex(speech, _REFUSAL_PATTERN)
        self.assertNotRegex(speech, _PHYSICAL_DEFLECTION_PATTERN)
        self.assertNotRegex(speech, _UNSUPPORTED_PERSON_NAME_PATTERN)
        self.assertNotRegex(speech, _UNSUPPORTED_RELATIONSHIP_PATTERN)
        self.assert_user_perspective(speech)

    def test_exact_failed_meeting_recall_end_to_end(self) -> None:
        reply = self.real_routed_conversation().send(
            "What is my preferred meeting time for the robotics project?"
        )

        self.assert_route_and_model(
            reply,
            RouteDecision(True, "small"),
            self.config.ollama.small_model,
        )
        self.assertEqual(
            reply.memory_diagnostics.model_used_ids,
            (MEETING_MEMORY_ID,),
        )
        self.assertIn(
            MEETING_MEMORY_ID, reply.memory_diagnostics.retrieved_ids
        )
        self.assertEqual(
            reply.memory_diagnostics.supplied_ids, (MEETING_MEMORY_ID,)
        )
        speech = reply.response.speech
        self.assertRegex(
            speech,
            re.compile(r"\btuesday mornings?\b", re.IGNORECASE),
        )
        self.assertRegex(speech, re.compile(r"\b(?:you|your)\b", re.I))
        self.assertNotRegex(speech, _NEGATED_MEETING_PATTERN)
        self.assert_no_invented_time_or_date(speech)
        self.assertNotRegex(speech, _REFUSAL_PATTERN)
        self.assertNotRegex(speech, _PHYSICAL_DEFLECTION_PATTERN)
        self.assertNotRegex(speech, re.compile(r"\bTheo\b", re.IGNORECASE))
        self.assertNotRegex(speech, _UNSUPPORTED_PERSON_NAME_PATTERN)
        self.assertNotRegex(speech, _UNSUPPORTED_RELATIONSHIP_PATTERN)
        self.assert_user_perspective(speech)

    def test_exact_failed_complex_plan_end_to_end(self) -> None:
        reply = self.real_routed_conversation().send(COMPLEX_PLAN_PROMPT)

        self.assert_route_and_model(
            reply,
            RouteDecision(True, "large"),
            self.config.ollama.large_model,
        )
        self.assertEqual(
            set(reply.memory_diagnostics.retrieved_ids), ALL_MEMORY_IDS
        )
        self.assertEqual(
            set(reply.memory_diagnostics.supplied_ids), ALL_MEMORY_IDS
        )
        self.assertEqual(
            set(reply.memory_diagnostics.model_used_ids), ALL_MEMORY_IDS
        )
        speech = reply.response.speech
        self.assert_three_concise_plan_steps(speech)
        self.assertRegex(speech, re.compile(r"\bTheo\b", re.IGNORECASE))
        self.assertRegex(
            speech, re.compile(r"\btuesday mornings?\b", re.IGNORECASE)
        )
        self.assertNotRegex(speech, _NEGATED_PARTNER_PATTERN)
        self.assertNotRegex(speech, _NEGATED_MEETING_PATTERN)
        self.assert_no_invented_time_or_date(speech)
        self.assertNotRegex(speech, _REFUSAL_PATTERN)
        self.assertNotRegex(speech, _PHYSICAL_DEFLECTION_PATTERN)
        self.assertNotRegex(speech, _UNSUPPORTED_PERSON_NAME_PATTERN)
        self.assertNotRegex(speech, _UNSUPPORTED_RELATIONSHIP_PATTERN)
        self.assert_user_perspective(speech)


if __name__ == "__main__":
    unittest.main()
