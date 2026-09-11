import json
import os
import socket
from copy import deepcopy
from io import BytesIO
from threading import Event, Lock, Thread, get_ident
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler

from oline_hri.config import load_config
from oline_hri.ollama import (
    ChatMessage,
    OllamaClient,
    OllamaError,
    OllamaTimeoutError,
)
from oline_hri.response import (
    ROBOT_RESPONSE_SCHEMA,
    ResponseValidationError,
    build_robot_response_schema,
    parse_robot_response,
)


class FakeResponse:
    def __init__(self, payload: object, *, raw: bool = False) -> None:
        self._body = payload if raw else json.dumps(payload).encode("utf-8")
        self.read_sizes = []

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._body if size < 0 else self._body[:size]


def successful_chat(
    model: str = "qwen3:0.6b", content: str = "Hello there."
) -> dict[str, object]:
    return {
        "model": model,
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": "stop",
    }


def successful_unload(model: str) -> dict[str, object]:
    return {
        "model": model,
        "response": "",
        "done": True,
        "done_reason": "unload",
    }


def unload_or_chat_response(
    request: object, chat_payload: object, *, raw: bool = False
) -> FakeResponse:
    if request.full_url.endswith("/api/generate"):
        requested_model = json.loads(request.data)["model"]
        return FakeResponse(successful_unload(requested_model))
    return FakeResponse(chat_payload, raw=raw)


def memory_id(digit: str) -> str:
    return "mem_" + digit * 32


class OllamaClientTests(unittest.TestCase):
    def test_grounded_chat_pseudonymizes_outbound_bytes_and_restores_only_citations(
        self,
    ) -> None:
        first = memory_id("1")
        second = memory_id("2")
        # Reversed numeric order proves aliases follow supplied order, not ID
        # sorting. A nested extra field in the model result proves restoration
        # is intentionally limited to top-level memory_used.
        schema = build_robot_response_schema(
            (second, first), require_citation=True
        )
        original_schema = deepcopy(schema)
        memory_message = ChatMessage(
            role="system",
            content=json.dumps(
                {
                    "records": [
                        {"id": second, "related": {"id": first}},
                    ]
                },
                separators=(",", ":"),
            ),
        )
        original_message_content = memory_message.content
        captured_chat_bytes = []

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            captured_chat_bytes.append(request.data)
            return FakeResponse(
                successful_chat(
                    content=json.dumps(
                        {
                            "speech": "The supplied records support this answer.",
                            "gesture_id": "NO_ACTION",
                            "memory_used": [
                                "memory_ref_2",
                                "memory_ref_1",
                                "memory_ref_2",
                            ],
                            "nested": {"citation": "memory_ref_1"},
                        },
                        separators=(",", ":"),
                    )
                )
            )

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        result = client.chat(
            config.ollama.small_model,
            [memory_message, ChatMessage(role="user", content=first)],
            response_format=schema,
        )

        self.assertEqual(len(captured_chat_bytes), 1)
        outbound = captured_chat_bytes[0]
        self.assertNotIn(first.encode("ascii"), outbound)
        self.assertNotIn(second.encode("ascii"), outbound)
        payload = json.loads(outbound)
        self.assertEqual(
            payload["format"]["properties"]["memory_used"]["items"]["enum"],
            ["memory_ref_1", "memory_ref_2"],
        )
        self.assertIn("memory_ref_1", payload["messages"][0]["content"])
        self.assertIn("memory_ref_2", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][1]["content"], "memory_ref_2")

        restored = json.loads(result.content)
        self.assertEqual(
            restored["memory_used"], [first, second, first]
        )
        self.assertEqual(restored["nested"]["citation"], "memory_ref_1")
        self.assertNotIn(first, restored["speech"])
        self.assertNotIn(second, restored["speech"])
        self.assertEqual(result.citation_annotations_removed, 0)
        self.assertEqual(schema, original_schema)
        self.assertEqual(memory_message.content, original_message_content)

    def test_grounded_aliases_are_stable_across_model_calls(self) -> None:
        first = memory_id("1")
        second = memory_id("2")
        schema = build_robot_response_schema((first, second))
        chat_payloads = []

        def opener(request, timeout):
            payload = json.loads(request.data)
            if request.full_url.endswith("/api/generate"):
                return FakeResponse(successful_unload(payload["model"]))
            chat_payloads.append(payload)
            return FakeResponse(
                successful_chat(
                    payload["model"],
                    '{"speech":"Fine.","gesture_id":"NO_ACTION",'
                    '"memory_used":["memory_ref_2"]}',
                )
            )

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        message = ChatMessage(role="user", content=f"Compare {first} and {second}")

        small = client.chat(
            config.ollama.small_model,
            [message],
            response_format=schema,
        )
        large = client.chat(
            config.ollama.large_model,
            [message],
            response_format=schema,
        )

        self.assertEqual(len(chat_payloads), 2)
        for payload in chat_payloads:
            self.assertEqual(
                payload["format"]["properties"]["memory_used"]["items"][
                    "enum"
                ],
                ["memory_ref_1", "memory_ref_2"],
            )
            self.assertEqual(
                payload["messages"][0]["content"],
                "Compare memory_ref_1 and memory_ref_2",
            )
        self.assertEqual(json.loads(small.content)["memory_used"], [second])
        self.assertEqual(json.loads(large.content)["memory_used"], [second])
        self.assertEqual(small.citation_annotations_removed, 0)
        self.assertEqual(large.citation_annotations_removed, 0)

    def test_grounded_request_rejects_unknown_ids_before_any_network_work(
        self,
    ) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        fullwidth_unknown = "ＭＥＭ＿" + "Ａ" * 32
        unknown_values = (
            memory_id("2"),
            "MEM_" + "A" * 32,
            fullwidth_unknown,
        )
        config = load_config()
        for unknown in unknown_values:
            with self.subTest(unknown=unknown):
                calls = []
                client = OllamaClient(
                    config.ollama,
                    config.generation,
                    opener=lambda request, timeout: calls.append(request),
                )
                with self.assertRaisesRegex(OllamaError, "unpseudonymized"):
                    client.chat(
                        config.ollama.small_model,
                        [
                            ChatMessage(
                                role="user",
                                content=f"Use {allowed}, ignore {unknown}",
                            )
                        ],
                        response_format=schema,
                    )
                self.assertEqual(calls, [])

    def test_grounded_request_rejects_reserved_alias_collisions_preflight(
        self,
    ) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        collisions = (
            "memory_ref_1",
            "MEMORY_REF_999",
            "ｍｅｍｏｒｙ＿ｒｅｆ＿７",
        )
        config = load_config()
        for collision in collisions:
            with self.subTest(collision=collision):
                calls = []
                client = OllamaClient(
                    config.ollama,
                    config.generation,
                    opener=lambda request, timeout: calls.append(request),
                )
                with self.assertRaisesRegex(OllamaError, "reserved"):
                    client.chat(
                        config.ollama.small_model,
                        [
                            ChatMessage(
                                role="user",
                                content=f"{allowed} and {collision}",
                            )
                        ],
                        response_format=schema,
                    )
                self.assertEqual(calls, [])

    def test_duplicate_memory_enum_fails_closed_before_network_work(self) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        schema["properties"]["memory_used"]["items"]["enum"].append(allowed)
        calls = []
        config = load_config()
        client = OllamaClient(
            config.ollama,
            config.generation,
            opener=lambda request, timeout: calls.append(request),
        )

        with self.assertRaisesRegex(OllamaError, "unpseudonymized"):
            client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content="Use supplied memory")],
                response_format=schema,
            )

        self.assertEqual(calls, [])

    def test_type_coerced_robot_schema_fails_closed_before_network_work(
        self,
    ) -> None:
        allowed = memory_id("1")
        config = load_config()
        mutations = (
            ("minItems", True),
            ("maxItems", 1.0),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                schema = build_robot_response_schema(
                    (allowed,), require_citation=True
                )
                schema["properties"]["memory_used"][field] = value
                calls = []
                client = OllamaClient(
                    config.ollama,
                    config.generation,
                    opener=lambda request, timeout: calls.append(request),
                )

                with self.assertRaisesRegex(OllamaError, "unpseudonymized"):
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content=allowed)],
                        response_format=schema,
                    )

                self.assertEqual(calls, [])

    def test_no_memory_robot_schema_preserves_payload_and_content(self) -> None:
        captured = []
        raw_content = (
            '{ "speech": "memory_ref_1 is ordinary text here", '
            '"gesture_id": "NO_ACTION", "memory_used": [] }'
        )

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            captured.append(json.loads(request.data))
            return FakeResponse(successful_chat(content=raw_content))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        result = client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content="An ordinary question")],
            response_format=ROBOT_RESPONSE_SCHEMA,
        )

        self.assertEqual(captured[0]["format"], ROBOT_RESPONSE_SCHEMA)
        self.assertEqual(result.content, raw_content)

    def test_invalid_memory_enum_does_not_activate_alias_translation(self) -> None:
        schema = build_robot_response_schema((memory_id("1"),))
        schema["properties"]["memory_used"]["items"]["enum"] = [
            "external_record_1"
        ]
        raw_content = (
            '{"speech":"memory_ref_1 stays ordinary text",'
            '"gesture_id":"NO_ACTION","memory_used":["memory_ref_1"]}'
        )
        captured = []

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            captured.append(json.loads(request.data))
            return FakeResponse(successful_chat(content=raw_content))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        result = client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content="memory_ref_1")],
            response_format=schema,
        )

        self.assertEqual(captured[0]["format"], schema)
        self.assertEqual(result.content, raw_content)
        self.assertEqual(result.citation_annotations_removed, 0)

    def test_grounded_exact_suffix_citations_are_removed_and_audited(
        self,
    ) -> None:
        first = memory_id("1")
        second = memory_id("2")
        schema = build_robot_response_schema(
            (first, second), require_citation=True
        )
        raw_speech = (
            "Friday was the ginger-tea correction (per memory_ref_1). "
            "Saturday was the navigation milestone (per memory_ref_2); "
            "therefore Saturday came later."
        )

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return FakeResponse(
                successful_chat(
                    content=json.dumps(
                        {
                            "speech": raw_speech,
                            "gesture_id": "NO_ACTION",
                            "memory_used": [
                                "memory_ref_1",
                                "memory_ref_2",
                            ],
                        }
                    )
                )
            )

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        result = client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content=f"Compare {first} and {second}")],
            response_format=schema,
        )

        expected_speech = (
            "Friday was the ginger-tea correction. "
            "Saturday was the navigation milestone; "
            "therefore Saturday came later."
        )
        restored = json.loads(result.content)
        self.assertEqual(restored["speech"], expected_speech)
        self.assertEqual(restored["memory_used"], [first, second])
        self.assertEqual(result.citation_annotations_removed, 2)
        parsed = parse_robot_response(
            result.content, allowed_memory_ids=(first, second)
        )
        self.assertEqual(parsed.speech, expected_speech)
        self.assertEqual(parsed.memory_used, (first, second))

    def test_grounded_adjacent_exact_suffix_citations_are_removed(
        self,
    ) -> None:
        first = memory_id("1")
        second = memory_id("2")
        schema = build_robot_response_schema((first, second))

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return FakeResponse(
                successful_chat(
                    content=json.dumps(
                        {
                            "speech": (
                                "Both records support this"
                                " (per memory_ref_1) (per memory_ref_2)."
                            ),
                            "gesture_id": "NO_ACTION",
                            "memory_used": [
                                "memory_ref_1",
                                "memory_ref_2",
                            ],
                        }
                    )
                )
            )

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        result = client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content=f"Use {first} and {second}")],
            response_format=schema,
        )

        self.assertEqual(
            json.loads(result.content)["speech"],
            "Both records support this.",
        )
        self.assertEqual(result.citation_annotations_removed, 2)

    def test_grounded_suffix_citation_must_be_declared_and_known(self) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        cases = (
            ("Claim (per memory_ref_1).", []),
            ("Claim (per memory_ref_9).", ["memory_ref_1"]),
        )
        config = load_config()
        for speech, memory_used in cases:
            with self.subTest(speech=speech, memory_used=memory_used):
                def opener(
                    request,
                    timeout,
                    speech=speech,
                    memory_used=memory_used,
                ):
                    if request.full_url.endswith("/api/generate"):
                        requested_model = json.loads(request.data)["model"]
                        return FakeResponse(successful_unload(requested_model))
                    return FakeResponse(
                        successful_chat(
                            content=json.dumps(
                                {
                                    "speech": speech,
                                    "gesture_id": "NO_ACTION",
                                    "memory_used": memory_used,
                                }
                            )
                        )
                    )

                client = OllamaClient(
                    config.ollama, config.generation, opener=opener
                )
                with self.assertRaisesRegex(OllamaError, "assistant speech"):
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content=allowed)],
                        response_format=schema,
                    )

    def test_grounded_near_miss_citation_annotations_are_never_removed(
        self,
    ) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        speech_values = (
            "Claim (from memory_ref_1).",
            "Claim (not per memory_ref_1).",
            "Claim (per memory_ref_1 because it is relevant).",
            "Claim per memory_ref_1.",
            "Claim(per memory_ref_1).",
            "Claim (per memory_ref_1) carefully.",
            "Claim (per MEMORY_REF_1).",
            "Claim (per ｍｅｍｏｒｙ＿ｒｅｆ＿１).",
            "Claim (ginger tea, per memory_ref_1).",
        )
        config = load_config()
        for speech in speech_values:
            with self.subTest(speech=speech):
                def opener(request, timeout, speech=speech):
                    if request.full_url.endswith("/api/generate"):
                        requested_model = json.loads(request.data)["model"]
                        return FakeResponse(successful_unload(requested_model))
                    return FakeResponse(
                        successful_chat(
                            content=json.dumps(
                                {
                                    "speech": speech,
                                    "gesture_id": "NO_ACTION",
                                    "memory_used": ["memory_ref_1"],
                                }
                            )
                        )
                    )

                client = OllamaClient(
                    config.ollama, config.generation, opener=opener
                )
                with self.assertRaisesRegex(OllamaError, "assistant speech"):
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content=allowed)],
                        response_format=schema,
                    )

    def test_grounded_malformed_json_is_preserved_for_downstream_validation(
        self,
    ) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        malformed_outputs = (
            (
                '{"speech":"first","speech":"second",'
                '"gesture_id":"NO_ACTION",'
                '"memory_used":["memory_ref_1"]}'
            ),
            (
                '{"speech":NaN,"gesture_id":"NO_ACTION",'
                '"memory_used":["memory_ref_1"]}'
            ),
            (
                '{"speech":"unfinished","gesture_id":"NO_ACTION",'
                '"memory_used":["memory_ref_1"]'
            ),
            (
                '{"speech":"Claim (per memory_ref_1).",'
                '"gesture_id":"NO_ACTION",'
                '"memory_used":["memory_ref_1"]'
            ),
        )
        config = load_config()
        for raw_content in malformed_outputs:
            with self.subTest(raw_content=raw_content):
                def opener(request, timeout, raw_content=raw_content):
                    if request.full_url.endswith("/api/generate"):
                        requested_model = json.loads(request.data)["model"]
                        return FakeResponse(successful_unload(requested_model))
                    return FakeResponse(successful_chat(content=raw_content))

                client = OllamaClient(
                    config.ollama, config.generation, opener=opener
                )
                result = client.chat(
                    config.ollama.small_model,
                    [ChatMessage(role="user", content=allowed)],
                    response_format=schema,
                )

                self.assertEqual(result.content, raw_content)
                self.assertEqual(result.citation_annotations_removed, 0)
                self.assertNotIn(allowed, result.content)
                with self.assertRaises(ResponseValidationError):
                    parse_robot_response(
                        result.content, allowed_memory_ids=(allowed,)
                    )

    def test_grounded_valid_json_rejects_any_reserved_alias_in_speech(
        self,
    ) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        speech_values = (
            "I used memory_ref_1.",
            "I used MEMORY_REF_999.",
            "I used ｍｅｍｏｒｙ＿ｒｅｆ＿７.",
        )
        config = load_config()
        for speech in speech_values:
            with self.subTest(speech=speech):
                def opener(request, timeout, speech=speech):
                    if request.full_url.endswith("/api/generate"):
                        requested_model = json.loads(request.data)["model"]
                        return FakeResponse(successful_unload(requested_model))
                    return FakeResponse(
                        successful_chat(
                            content=json.dumps(
                                {
                                    "speech": speech,
                                    "gesture_id": "NO_ACTION",
                                    "memory_used": ["memory_ref_1"],
                                }
                            )
                        )
                    )

                client = OllamaClient(
                    config.ollama, config.generation, opener=opener
                )
                with self.assertRaisesRegex(OllamaError, "assistant speech"):
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content=allowed)],
                        response_format=schema,
                    )

    def test_grounded_confusable_alias_fails_closed(
        self,
    ) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        speeches = (
            "Friday came before Saturday (per mem\u043ery_ref_1).",
            "Friday came before Saturday (per memory_ref_\u0661).",
        )
        config = load_config()

        for speech in speeches:
            with self.subTest(speech=speech):
                def opener(request, timeout, speech=speech):
                    if request.full_url.endswith("/api/generate"):
                        requested_model = json.loads(request.data)["model"]
                        return FakeResponse(successful_unload(requested_model))
                    return FakeResponse(
                        successful_chat(
                            content=json.dumps(
                                {
                                    "speech": speech,
                                    "gesture_id": "NO_ACTION",
                                    "memory_used": ["memory_ref_1"],
                                }
                            )
                        )
                    )

                client = OllamaClient(
                    config.ollama, config.generation, opener=opener
                )
                with self.assertRaisesRegex(OllamaError, "assistant speech"):
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content=allowed)],
                        response_format=schema,
                    )

    def test_grounded_response_rejects_direct_internal_id_citation(self) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return FakeResponse(
                successful_chat(
                    content=json.dumps(
                        {
                            "speech": "A guessed ID must not be trusted.",
                            "gesture_id": "NO_ACTION",
                            "memory_used": [allowed],
                        }
                    )
                )
            )

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        with self.assertRaisesRegex(OllamaError, "internal memory ID"):
            client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content=allowed)],
                response_format=schema,
            )

    def test_zero_width_split_alias_in_speech_fails_downstream(self) -> None:
        allowed = memory_id("1")
        schema = build_robot_response_schema((allowed,))
        split_alias = "memory_ref_\u200b1"

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return FakeResponse(
                successful_chat(
                    content=json.dumps(
                        {
                            "speech": f"Do not expose {split_alias}.",
                            "gesture_id": "NO_ACTION",
                            "memory_used": ["memory_ref_1"],
                        }
                    )
                )
            )

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        result = client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content=allowed)],
            response_format=schema,
        )

        self.assertEqual(json.loads(result.content)["memory_used"], [allowed])
        with self.assertRaisesRegex(ResponseValidationError, "unsafe control"):
            parse_robot_response(
                result.content, allowed_memory_ids=(allowed,)
            )

    def test_chat_sends_expected_small_model_payload(self) -> None:
        captured = []

        def opener(request, timeout):
            captured.append((request, timeout))
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return FakeResponse(
                {
                    "model": "qwen3:0.6b",
                    "message": {"role": "assistant", "content": "Hello there."},
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": 2_000_000_000,
                    "load_duration": 10,
                    "prompt_eval_count": 12,
                    "prompt_eval_duration": 250_000_000,
                    "eval_count": 20,
                    "eval_duration": 500_000_000,
                }
            )

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        result = client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content="Hello")],
            response_format=ROBOT_RESPONSE_SCHEMA,
        )

        self.assertEqual(len(captured), 2)
        for (unload_request, unload_timeout), expected_model in zip(
            captured[:1],
            (config.ollama.general_large_model,),
        ):
            self.assertTrue(unload_request.full_url.endswith("/api/generate"))
            self.assertEqual(unload_request.method, "POST")
            self.assertEqual(
                json.loads(unload_request.data),
                {
                    "model": expected_model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": 0,
                },
            )
            self.assertEqual(unload_timeout, 30)

        chat_request, chat_timeout = captured[1]
        self.assertTrue(chat_request.full_url.endswith("/api/chat"))
        self.assertEqual(chat_request.method, "POST")
        payload = json.loads(chat_request.data)
        self.assertEqual(payload["model"], "qwen3:0.6b")
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["keep_alive"], -1)
        self.assertEqual(payload["options"]["num_ctx"], 2048)
        self.assertEqual(payload["options"]["num_predict"], 192)
        self.assertEqual(payload["options"]["temperature"], 0.0)
        self.assertNotIn("seed", payload["options"])
        self.assertEqual(payload["format"], ROBOT_RESPONSE_SCHEMA)
        self.assertEqual(chat_timeout, 60)
        self.assertEqual(result.content, "Hello there.")
        self.assertEqual(result.prompt_eval_duration_ns, 250_000_000)
        self.assertEqual(result.generation_tokens_per_second, 40.0)

    def test_per_call_sampling_overrides_are_sent_without_changing_limits(
        self,
    ) -> None:
        captured = []

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            captured.append(json.loads(request.data))
            return FakeResponse(
                {
                    "model": "qwen3:0.6b",
                    "message": {"role": "assistant", "content": "{}"},
                    "done": True,
                    "done_reason": "stop",
                }
            )

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content="Classify")],
            temperature=0.0,
            seed=42,
        )

        self.assertEqual(len(captured), 1)
        options = captured[0]["options"]
        self.assertEqual(
            options,
            {
                "num_ctx": config.generation.context_length,
                "num_predict": config.generation.max_output_tokens,
                "temperature": 0.0,
                "seed": 42,
            },
        )

    def test_invalid_sampling_overrides_are_rejected_before_network_work(
        self,
    ) -> None:
        calls = []

        def opener(request, timeout):
            calls.append(request)
            raise AssertionError("opener must not run")

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        cases = (
            {"temperature": True},
            {"temperature": "0"},
            {"temperature": float("nan")},
            {"temperature": float("inf")},
            {"temperature": -0.1},
            {"temperature": 2.1},
            {"seed": True},
            {"seed": 1.5},
            {"seed": -1},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content="Classify")],
                        **overrides,
                    )
        self.assertEqual(calls, [])

    def test_unconfigured_model_is_rejected_before_network_work(self) -> None:
        calls = []

        def opener(request, timeout):
            calls.append(request)
            raise AssertionError("opener must not run")

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        with self.assertRaisesRegex(ValueError, "configured"):
            client.chat(
                "qwen3:8b",
                [ChatMessage(role="user", content="Bypass the scheduler")],
            )

        self.assertEqual(calls, [])

    def test_large_model_unloads_small_and_expires_after_generation(self) -> None:
        requests = []

        def opener(request, timeout):
            payload = json.loads(request.data)
            requests.append((request.full_url, payload, timeout))
            if request.full_url.endswith("/api/generate"):
                return FakeResponse(successful_unload(payload["model"]))
            return FakeResponse(successful_chat(payload["model"], "large reply"))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        result = client.chat(
            config.ollama.large_model,
            [ChatMessage(role="user", content="Use the large model")],
        )

        self.assertEqual(result.model, config.ollama.large_model)
        self.assertEqual(len(requests), 2)
        for request, expected_model in zip(
            requests[:1],
            (config.ollama.small_model,),
        ):
            self.assertTrue(request[0].endswith("/api/generate"))
            self.assertEqual(
                request[1],
                {
                    "model": expected_model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": 0,
                },
            )
            self.assertEqual(request[2], 30)
        self.assertTrue(requests[1][0].endswith("/api/chat"))
        self.assertEqual(requests[1][1]["model"], config.ollama.large_model)
        self.assertEqual(requests[1][1]["keep_alive"], 0)
        self.assertEqual(requests[1][2], 120)

    def test_general_large_model_unloads_small_and_expires(self) -> None:
        requests = []

        def opener(request, timeout):
            payload = json.loads(request.data)
            requests.append((request.full_url.rsplit("/", 1)[-1], payload))
            if request.full_url.endswith("/api/generate"):
                return FakeResponse(successful_unload(payload["model"]))
            return FakeResponse(successful_chat(payload["model"]))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        result = client.chat(
            config.ollama.general_large_model,
            [ChatMessage(role="user", content="Create a detailed plan")],
        )

        self.assertEqual(result.model, config.ollama.general_large_model)
        self.assertEqual(
            [(endpoint, payload["model"]) for endpoint, payload in requests],
            [
                ("generate", config.ollama.small_model),
                ("chat", config.ollama.general_large_model),
            ],
        )
        self.assertEqual(requests[-1][1]["keep_alive"], 0)

    def test_repeated_small_calls_do_not_repeat_peer_unload(self) -> None:
        requests = []

        def opener(request, timeout):
            payload = json.loads(request.data)
            requests.append((request.full_url, payload))
            if request.full_url.endswith("/api/generate"):
                return FakeResponse(successful_unload(payload["model"]))
            return FakeResponse(successful_chat(payload["model"]))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        message = [ChatMessage(role="user", content="Stay on the small model")]

        client.chat(config.ollama.small_model, message)
        client.chat(config.ollama.small_model, message)

        self.assertEqual(
            [url.rsplit("/", 1)[-1] for url, _ in requests],
            ["generate", "chat", "chat"],
        )
        self.assertEqual(
            [payload["model"] for _, payload in requests[:1]],
            [config.ollama.general_large_model],
        )
        self.assertEqual(
            [payload["keep_alive"] for _, payload in requests[1:]],
            [-1, -1],
        )

    def test_unload_all_establishes_and_reuses_known_empty_state(self) -> None:
        unloaded = []

        def opener(request, timeout):
            self.assertTrue(request.full_url.endswith("/api/generate"))
            payload = json.loads(request.data)
            unloaded.append(payload["model"])
            return FakeResponse(successful_unload(payload["model"]))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        client.unload_all()
        client.unload_all()

        self.assertEqual(
            unloaded,
            [
                config.ollama.small_model,
                config.ollama.general_large_model,
            ],
        )

    def test_unload_all_releases_only_the_known_resident_model(self) -> None:
        requests = []

        def opener(request, timeout):
            payload = json.loads(request.data)
            requests.append((request.full_url.rsplit("/", 1)[-1], payload["model"]))
            if request.full_url.endswith("/api/generate"):
                return FakeResponse(successful_unload(payload["model"]))
            return FakeResponse(successful_chat(payload["model"]))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content="Load the small model")],
        )

        client.unload_all()
        client.unload_all()

        self.assertEqual(
            requests,
            [
                ("generate", config.ollama.general_large_model),
                ("chat", config.ollama.small_model),
                ("generate", config.ollama.small_model),
            ],
        )

    def test_failed_unload_all_forgets_residency_and_retries_both(self) -> None:
        attempted = []
        fail_once = True

        def opener(request, timeout):
            nonlocal fail_once
            payload = json.loads(request.data)
            attempted.append(payload["model"])
            if fail_once:
                fail_once = False
                raise URLError("private server detail")
            return FakeResponse(successful_unload(payload["model"]))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        with self.assertRaises(OllamaError):
            client.unload_all()
        client.unload_all()

        self.assertEqual(
            attempted,
            [
                config.ollama.small_model,
                config.ollama.small_model,
                config.ollama.general_large_model,
            ],
        )

    def test_switching_small_to_large_explicitly_unloads_small(self) -> None:
        requests = []

        def opener(request, timeout):
            payload = json.loads(request.data)
            requests.append((request.full_url, payload))
            if request.full_url.endswith("/api/generate"):
                return FakeResponse(successful_unload(payload["model"]))
            return FakeResponse(successful_chat(payload["model"]))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        message = [ChatMessage(role="user", content="Switch models")]

        client.chat(config.ollama.small_model, message)
        client.chat(config.ollama.large_model, message)

        self.assertEqual(
            [
                (url.rsplit("/", 1)[-1], payload["model"])
                for url, payload in requests
            ],
            [
                ("generate", config.ollama.general_large_model),
                ("chat", config.ollama.small_model),
                ("generate", config.ollama.small_model),
                ("chat", config.ollama.large_model),
            ],
        )
        self.assertEqual(requests[-1][1]["keep_alive"], 0)

    def test_unload_response_is_validated_before_target_generation(self) -> None:
        config = load_config()
        peer = config.ollama.large_model
        cases = (
            ("invalid JSON", b"not-json", True),
            ("non-object", [], False),
            ("API error", {"error": "unload refused"}, False),
            (
                "incomplete",
                {
                    "model": peer,
                    "response": "",
                    "done": False,
                    "done_reason": "unload",
                },
                False,
            ),
            (
                "wrong model",
                successful_unload(config.ollama.small_model),
                False,
            ),
            (
                "nonempty response",
                {
                    "model": peer,
                    "response": "unexpected",
                    "done": True,
                    "done_reason": "unload",
                },
                False,
            ),
            (
                "wrong reason",
                {
                    "model": peer,
                    "response": "",
                    "done": True,
                    "done_reason": "stop",
                },
                False,
            ),
        )
        for name, response_payload, raw in cases:
            with self.subTest(name=name):
                calls = []

                def opener(request, timeout):
                    calls.append(request)
                    return FakeResponse(response_payload, raw=raw)

                client = OllamaClient(
                    config.ollama, config.generation, opener=opener
                )
                with self.assertRaises(OllamaError):
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content="Do not run yet")],
                    )

                self.assertEqual(len(calls), 1)
                self.assertTrue(calls[0].full_url.endswith("/api/generate"))

    def test_model_transaction_lock_prevents_request_interleaving(self) -> None:
        calls = []
        calls_lock = Lock()
        first_unload_started = Event()
        release_first_unload = Event()
        first_chat_started = Event()
        release_first_chat = Event()
        second_calling = Event()
        overlapping_network_call = Event()
        owner_ident = None

        def opener(request, timeout):
            nonlocal owner_ident
            caller_ident = get_ident()
            payload = json.loads(request.data)
            endpoint = request.full_url.rsplit("/", 1)[-1]
            with calls_lock:
                if owner_ident is None:
                    owner_ident = caller_ident
                if (
                    caller_ident != owner_ident
                    and not release_first_chat.is_set()
                ):
                    overlapping_network_call.set()
                calls.append((endpoint, payload["model"]))
                call_number = len(calls)

            if call_number == 1:
                first_unload_started.set()
                if not release_first_unload.wait(timeout=5):
                    raise AssertionError("first unload was not released")
            elif caller_ident == owner_ident and endpoint == "chat":
                first_chat_started.set()
                if not release_first_chat.wait(timeout=5):
                    raise AssertionError("first chat was not released")

            if endpoint == "generate":
                return FakeResponse(successful_unload(payload["model"]))
            return FakeResponse(successful_chat(payload["model"]))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        results = []
        errors = []

        def run_chat(model, content, started=None):
            if started is not None:
                started.set()
            try:
                results.append(
                    client.chat(model, [ChatMessage(role="user", content=content)])
                )
            except BaseException as exc:
                errors.append(exc)

        first = Thread(
            target=run_chat,
            args=(config.ollama.small_model, "first transaction"),
            daemon=True,
        )
        second = Thread(
            target=run_chat,
            args=(
                config.ollama.large_model,
                "second transaction",
                second_calling,
            ),
            daemon=True,
        )
        first.start()
        self.assertTrue(first_unload_started.wait(timeout=5))
        second.start()
        self.assertTrue(second_calling.wait(timeout=5))

        try:
            self.assertFalse(overlapping_network_call.wait(timeout=0.2))
            release_first_unload.set()
            self.assertTrue(first_chat_started.wait(timeout=5))
            self.assertFalse(overlapping_network_call.wait(timeout=0.2))
        finally:
            release_first_unload.set()
            release_first_chat.set()
            first.join(timeout=5)
            second.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(
            calls,
            [
                ("generate", config.ollama.general_large_model),
                ("chat", config.ollama.small_model),
                ("generate", config.ollama.small_model),
                ("chat", config.ollama.large_model),
            ],
        )

    def test_chat_failure_releases_lock_and_rechecks_unknown_state(self) -> None:
        calls = []
        fail_first_chat = True

        def opener(request, timeout):
            nonlocal fail_first_chat
            payload = json.loads(request.data)
            endpoint = request.full_url.rsplit("/", 1)[-1]
            calls.append((endpoint, payload["model"]))
            if endpoint == "generate":
                return FakeResponse(successful_unload(payload["model"]))
            if fail_first_chat:
                fail_first_chat = False
                raise URLError("generation disconnected")
            return FakeResponse(successful_chat(payload["model"], "recovered"))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        message = [ChatMessage(role="user", content="Recover safely")]
        with self.assertRaises(OllamaError):
            client.chat(config.ollama.small_model, message)

        recovery_done = Event()
        recovery_results = []
        recovery_errors = []

        def recover():
            try:
                recovery_results.append(
                    client.chat(config.ollama.small_model, message)
                )
            except BaseException as exc:
                recovery_errors.append(exc)
            finally:
                recovery_done.set()

        worker = Thread(target=recover, daemon=True)
        worker.start()
        self.assertTrue(recovery_done.wait(timeout=5))
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(recovery_errors, [])
        self.assertEqual(recovery_results[0].content, "recovered")
        self.assertEqual(
            calls,
            [
                ("generate", config.ollama.general_large_model),
                ("chat", config.ollama.small_model),
                ("generate", config.ollama.general_large_model),
                ("chat", config.ollama.small_model),
            ],
        )

    def test_unload_failure_releases_lock_and_retries_unload(self) -> None:
        calls = []
        fail_first_unload = True

        def opener(request, timeout):
            nonlocal fail_first_unload
            payload = json.loads(request.data)
            endpoint = request.full_url.rsplit("/", 1)[-1]
            calls.append((endpoint, payload["model"]))
            if endpoint == "generate" and fail_first_unload:
                fail_first_unload = False
                raise URLError("unload disconnected")
            if endpoint == "generate":
                return FakeResponse(successful_unload(payload["model"]))
            return FakeResponse(successful_chat(payload["model"], "recovered"))

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        message = [ChatMessage(role="user", content="Retry unload")]
        with self.assertRaises(OllamaError):
            client.chat(config.ollama.small_model, message)

        recovery_done = Event()
        recovery_errors = []

        def recover():
            try:
                client.chat(config.ollama.small_model, message)
            except BaseException as exc:
                recovery_errors.append(exc)
            finally:
                recovery_done.set()

        worker = Thread(target=recover, daemon=True)
        worker.start()
        self.assertTrue(recovery_done.wait(timeout=5))
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(recovery_errors, [])
        self.assertEqual(
            calls,
            [
                ("generate", config.ollama.general_large_model),
                ("generate", config.ollama.general_large_model),
                ("chat", config.ollama.small_model),
            ],
        )

    def test_default_opener_explicitly_disables_environment_proxies(self) -> None:
        captured = {}

        def safe_open(request, timeout):
            captured.setdefault("requests", []).append(request)
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return FakeResponse(
                {
                    "model": "qwen3:0.6b",
                    "message": {"role": "assistant", "content": "safe"},
                    "done": True,
                }
            )

        class FakeOpenerDirector:
            open = staticmethod(safe_open)

        hostile_proxy_environment = {
            "HTTP_PROXY": "http://remote-proxy.invalid:8080",
            "HTTPS_PROXY": "http://remote-proxy.invalid:8080",
            "http_proxy": "http://remote-proxy.invalid:8080",
            "https_proxy": "http://remote-proxy.invalid:8080",
            "NO_PROXY": "",
            "no_proxy": "",
        }
        config = load_config()
        with patch.dict(os.environ, hostile_proxy_environment, clear=False):
            with patch("oline_hri.ollama.build_opener") as builder:
                builder.return_value = FakeOpenerDirector()
                client = OllamaClient(config.ollama, config.generation)

                result = client.chat(
                    config.ollama.small_model,
                    [ChatMessage(role="user", content="private prompt")],
                )

        builder.assert_called_once()
        handlers = builder.call_args.args
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], ProxyHandler)
        self.assertEqual(handlers[0].proxies, {})
        self.assertEqual(result.content, "safe")
        self.assertEqual(len(captured["requests"]), 2)

    def test_injected_opener_is_preserved_without_building_a_default(self) -> None:
        calls = []

        def opener(request, timeout):
            calls.append(request)
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return FakeResponse(
                {
                    "model": "qwen3:0.6b",
                    "message": {"role": "assistant", "content": "custom"},
                    "done": True,
                }
            )

        config = load_config()
        with patch("oline_hri.ollama.build_opener") as builder:
            client = OllamaClient(
                config.ollama, config.generation, opener=opener
            )
            result = client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content="Hello")],
            )

        builder.assert_not_called()
        self.assertEqual(result.content, "custom")
        self.assertEqual(len(calls), 2)

    def test_network_failure_becomes_ollama_error(self) -> None:
        def opener(request, timeout):
            raise URLError("connection refused")

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        with self.assertRaisesRegex(OllamaError, "cannot reach Ollama"):
            client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content="Hello")],
            )

    def test_timeout_failures_are_typed_and_sanitized(self) -> None:
        private_detail = "private prompt echoed by transport"
        failures = (
            TimeoutError(private_detail),
            socket.timeout(private_detail),
            URLError(TimeoutError(private_detail)),
            URLError(socket.timeout(private_detail)),
        )
        config = load_config()
        for failure in failures:
            with self.subTest(failure_type=type(failure).__name__):

                def opener(request, timeout):
                    if request.full_url.endswith("/api/generate"):
                        requested_model = json.loads(request.data)["model"]
                        return FakeResponse(successful_unload(requested_model))
                    raise failure

                client = OllamaClient(
                    config.ollama, config.generation, opener=opener
                )
                with self.assertRaises(OllamaTimeoutError) as caught:
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content="private prompt")],
                    )

                self.assertEqual(str(caught.exception), "Ollama request timed out")
                self.assertNotIn(private_detail, str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)

    def test_transport_and_server_errors_are_sanitized(self) -> None:
        private_detail = "private backend detail"
        config = load_config()
        failures = (
            URLError(private_detail),
            OSError(private_detail),
            HTTPError(
                config.ollama.base_url,
                503,
                private_detail,
                None,
                BytesIO(json.dumps({"error": private_detail}).encode("utf-8")),
            ),
        )
        for failure in failures:
            with self.subTest(failure_type=type(failure).__name__):

                def failing_opener(request, timeout):
                    raise failure

                client = OllamaClient(
                    config.ollama,
                    config.generation,
                    opener=failing_opener,
                )
                with self.assertRaises(OllamaError) as caught:
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content="private prompt")],
                    )

                expected = (
                    "Ollama HTTP 503"
                    if isinstance(failure, HTTPError)
                    else "cannot reach Ollama"
                )
                self.assertEqual(str(caught.exception), expected)
                self.assertNotIn(private_detail, str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)

        def api_error_opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return FakeResponse({"error": private_detail})

        client = OllamaClient(
            config.ollama, config.generation, opener=api_error_opener
        )
        with self.assertRaises(OllamaError) as caught:
            client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content="private prompt")],
            )
        self.assertEqual(
            str(caught.exception), "Ollama returned an error response"
        )
        self.assertNotIn(private_detail, str(caught.exception))

    def test_response_body_at_exactly_64_kib_is_accepted(self) -> None:
        encoded = json.dumps(successful_chat()).encode("utf-8")
        exact_body = encoded + b" " * (64 * 1024 - len(encoded))
        exact_response = FakeResponse(exact_body, raw=True)

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return exact_response

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        result = client.chat(
            config.ollama.small_model,
            [ChatMessage(role="user", content="Hello")],
        )

        self.assertEqual(result.content, "Hello there.")
        self.assertEqual(exact_response.read_sizes, [64 * 1024 + 1])

    def test_response_body_is_capped_at_64_kib(self) -> None:
        private_detail = b"private oversized model output"
        oversized = private_detail + b"x" * (64 * 1024 + 1)
        oversized_response = FakeResponse(oversized, raw=True)

        def opener(request, timeout):
            if request.full_url.endswith("/api/generate"):
                requested_model = json.loads(request.data)["model"]
                return FakeResponse(successful_unload(requested_model))
            return oversized_response

        config = load_config()
        client = OllamaClient(config.ollama, config.generation, opener=opener)

        with self.assertRaises(OllamaError) as caught:
            client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content="private prompt")],
            )

        self.assertEqual(
            str(caught.exception), "Ollama response exceeded size limit"
        )
        self.assertNotIn(private_detail.decode("ascii"), str(caught.exception))
        self.assertEqual(oversized_response.read_sizes, [64 * 1024 + 1])

    def test_incomplete_response_is_rejected(self) -> None:
        config = load_config()
        client = OllamaClient(
            config.ollama,
            config.generation,
            opener=lambda request, timeout: unload_or_chat_response(
                request, {"done": False}
            ),
        )

        with self.assertRaisesRegex(OllamaError, "incomplete"):
            client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content="Hello")],
            )

    def test_chat_requires_exact_model_and_assistant_role_metadata(self) -> None:
        config = load_config()
        cases = (
            (
                "missing model",
                {
                    "message": {"role": "assistant", "content": "Hello"},
                    "done": True,
                },
            ),
            (
                "wrong model",
                successful_chat(config.ollama.large_model),
            ),
            (
                "wrong role",
                {
                    "model": config.ollama.small_model,
                    "message": {"role": "user", "content": "Hello"},
                    "done": True,
                },
            ),
            (
                "missing role",
                {
                    "model": config.ollama.small_model,
                    "message": {"content": "Hello"},
                    "done": True,
                },
            ),
        )
        for label, payload in cases:
            with self.subTest(label=label):
                client = OllamaClient(
                    config.ollama,
                    config.generation,
                    opener=lambda request, timeout, payload=payload: (
                        unload_or_chat_response(request, payload)
                    ),
                )

                with self.assertRaises(OllamaError):
                    client.chat(
                        config.ollama.small_model,
                        [ChatMessage(role="user", content="Hello")],
                    )

    def test_invalid_json_is_rejected(self) -> None:
        config = load_config()
        client = OllamaClient(
            config.ollama,
            config.generation,
            opener=lambda request, timeout: unload_or_chat_response(
                request, b"not-json", raw=True
            ),
        )

        with self.assertRaisesRegex(OllamaError, "invalid JSON"):
            client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content="Hello")],
            )

    def test_empty_assistant_message_is_rejected(self) -> None:
        config = load_config()
        client = OllamaClient(
            config.ollama,
            config.generation,
            opener=lambda request, timeout: unload_or_chat_response(
                request,
                {
                    "model": config.ollama.small_model,
                    "done": True,
                    "message": {"role": "assistant", "content": " "},
                },
            ),
        )

        with self.assertRaisesRegex(OllamaError, "empty assistant message"):
            client.chat(
                config.ollama.small_model,
                [ChatMessage(role="user", content="Hello")],
            )


if __name__ == "__main__":
    unittest.main()
