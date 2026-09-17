from dataclasses import replace
import math
import unittest

from oline_hri.memory import (
    KeywordMatch,
    MemoryItem,
    MemoryStoreError,
    MemoryValidationError,
    SemanticMatch,
)
from oline_hri.retrieval import (
    CANDIDATE_POOL_SIZE,
    DEFAULT_RETRIEVAL_LIMIT,
    MAX_RETRIEVAL_LIMIT,
    RRF_K,
    HybridMatch,
    HybridRetriever,
    RetrievalError,
)


def memory(number: int, text: str | None = None) -> MemoryItem:
    timestamp = "2026-09-06T00:00:00.000000Z"
    return MemoryItem(
        id=f"mem_{number:032x}",
        profile_id="alice",
        kind="fact",
        canonical_text=text or f"Memory {number}.",
        source_turn_id=None,
        event_time=None,
        sensitivity="normal",
        consent_status="confirmed",
        confidence=1.0,
        importance=3,
        status="active",
        supersedes_id=None,
        valid_from=timestamp,
        valid_until=None,
        retention_until=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


class FakeMemorySearch:
    def __init__(self) -> None:
        self.semantic_results = ()
        self.keyword_results = ()
        self.semantic_error = None
        self.keyword_error = None
        self.snapshot_result = True
        self.snapshot_error = None
        self.calls = []
        self.snapshot_calls = []

    def search_semantic(self, query, *, limit=5):
        self.calls.append(("semantic", query, limit))
        if self.semantic_error is not None:
            raise self.semantic_error
        return self.semantic_results

    def search_keywords(self, query, *, limit=5):
        self.calls.append(("keyword", query, limit))
        if self.keyword_error is not None:
            raise self.keyword_error
        return self.keyword_results

    def retrieval_snapshot_is_current(self, items):
        self.snapshot_calls.append(tuple(items))
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return self.snapshot_result


class HybridRetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeMemorySearch()
        self.retriever = HybridRetriever(self.backend)

    def test_contract_constants_are_fixed_and_bounded(self) -> None:
        self.assertEqual(RRF_K, 60)
        self.assertEqual(CANDIDATE_POOL_SIZE, 20)
        self.assertEqual(DEFAULT_RETRIEVAL_LIMIT, 3)
        self.assertEqual(MAX_RETRIEVAL_LIMIT, 5)

    def test_reranker_covers_inventory_and_preference_without_extra_searches(self) -> None:
        distractors = (
            memory(1, "Your materials budget is 19 credits."),
            memory(2, "Your materials box contains four cords."),
            memory(3, "Your next workshop is on 4 October 2026."),
        )
        inventory = memory(4, "You have nine cards available for table labels and badges.")
        duplicate_topic = memory(5, "You have four cards available for badges.")
        preference = memory(6, "You want only first names on badges.")
        items = distractors + (inventory, duplicate_topic, preference)
        self.backend.semantic_results = tuple(SemanticMatch(item, 0.9 - i * 0.1)
                                              for i, item in enumerate(items))
        self.backend.keyword_results = tuple(KeywordMatch(item, -10 + i)
                                             for i, item in enumerate(items))
        query = ("Using my stored card supply and badge preference, "
                 "allocate 2 cards to labels and the remaining cards to badges.")
        matches = self.retriever.retrieve(query, limit=2)
        self.assertEqual({match.memory.id for match in matches}, {inventory.id, preference.id})
        self.assertEqual(self.backend.calls, [
            ("semantic", query, CANDIDATE_POOL_SIZE),
            ("keyword", query, CANDIDATE_POOL_SIZE),
        ])
        by_id = {match.memory.id: match for match in matches}
        self.assertEqual(by_id[inventory.id].semantic_position, 4)
        self.assertEqual(by_id[preference.id].keyword_position, 6)
        self.assertAlmostEqual(by_id[preference.id].fused_score, 2 / (RRF_K + 6))
        self.assertTrue(self.retriever.is_current(matches))
        self.assertEqual(self.backend.snapshot_calls, [tuple(match.memory for match in matches)])

    def test_same_event_conflicts_outrank_shared_date_and_wrong_owner(self) -> None:
        items = (
            memory(1, "Your knitting workshop on 8 October 2026 is in North Hall."),
            memory(2, "Rina's optics workshop on 8 October 2026 is in West Hall."),
            memory(3, "Your optics workshop on 8 October 2026 is in South Hall."),
            memory(4, "Your optics workshop on 8 October 2026 is in East Hall."),
        )
        self.backend.semantic_results = tuple(SemanticMatch(item, 0.9) for item in items)
        matches = self.retriever.retrieve(
            "Which room is booked for my optics workshop on 8 October 2026?", limit=2,
        )
        self.assertEqual([match.memory for match in matches], list(items[2:]))
        self.assertEqual([match.semantic_position for match in matches], [3, 4])

    def test_reranking_cannot_recover_an_item_outside_the_frozen_candidate_cap(self) -> None:
        items = tuple(memory(i, "You prefer tea.") for i in range(1, 21))
        omitted = memory(21, "Your optics workshop is in East Hall.")
        self.backend.semantic_results = tuple(SemanticMatch(item, 0.9) for item in items + (omitted,))
        matches = self.retriever.retrieve("Which room is booked for my optics workshop?")
        self.assertNotIn(omitted.id, [match.memory.id for match in matches])
        self.assertEqual(len(matches), DEFAULT_RETRIEVAL_LIMIT)
        self.assertEqual(len(self.backend.calls), 2)

    def test_overlap_is_deduplicated_and_fused_by_one_based_positions(self) -> None:
        first = memory(1)
        overlap = memory(2)
        keyword_only = memory(3)
        self.backend.semantic_results = (
            SemanticMatch(first, 0.99),
            SemanticMatch(overlap, 0.75),
        )
        self.backend.keyword_results = (
            KeywordMatch(overlap, -12.5),
            KeywordMatch(keyword_only, -3.0),
        )

        matches = self.retriever.retrieve("personal question", limit=5)

        self.assertEqual(
            self.backend.calls,
            [
                ("semantic", "personal question", CANDIDATE_POOL_SIZE),
                ("keyword", "personal question", CANDIDATE_POOL_SIZE),
            ],
        )
        self.assertEqual(
            [match.memory.id for match in matches],
            [overlap.id, first.id, keyword_only.id],
        )
        fused = matches[0]
        self.assertAlmostEqual(
            fused.fused_score,
            1.0 / (RRF_K + 2) + 1.0 / (RRF_K + 1),
        )
        self.assertEqual(fused.semantic_position, 2)
        self.assertEqual(fused.keyword_position, 1)
        self.assertEqual(fused.semantic_score, 0.75)
        self.assertEqual(fused.keyword_rank, -12.5)
        self.assertEqual(fused.sources, ("semantic", "keyword"))
        self.assertEqual(matches[1].sources, ("semantic",))
        self.assertEqual(matches[2].sources, ("keyword",))

    def test_raw_source_values_never_break_equal_weight_ties(self) -> None:
        lower_id = memory(1)
        higher_id = memory(2)
        self.backend.semantic_results = (SemanticMatch(higher_id, -999.0),)
        self.backend.keyword_results = (KeywordMatch(lower_id, 999999.0),)

        matches = self.retriever.retrieve("tie")

        self.assertEqual(matches[0].fused_score, matches[1].fused_score)
        self.assertEqual(
            [match.memory.id for match in matches], [lower_id.id, higher_id.id]
        )
        self.assertEqual(matches[0].keyword_rank, 999999.0)
        self.assertEqual(matches[1].semantic_score, -999.0)

    def test_equal_rrf_positions_preserve_exact_lexical_candidate(self) -> None:
        semantic_lower_id = memory(1)
        keyword_higher_id = memory(2)
        self.backend.semantic_results = (
            SemanticMatch(semantic_lower_id, 0.999),
        )
        self.backend.keyword_results = (
            KeywordMatch(keyword_higher_id, -50.0),
        )

        match = self.retriever.retrieve("exact personal name", limit=1)[0]

        self.assertEqual(match.memory, keyword_higher_id)
        self.assertEqual(match.sources, ("keyword",))

    def test_default_limit_max_limit_and_fixed_candidate_pool(self) -> None:
        all_items = tuple(memory(number) for number in range(1, 26))
        self.backend.semantic_results = tuple(
            SemanticMatch(item, 1.0 - index / 100.0)
            for index, item in enumerate(all_items)
        )

        default_matches = self.retriever.retrieve("many")
        maximum_matches = self.retriever.retrieve("many", limit=5)

        self.assertEqual(len(default_matches), DEFAULT_RETRIEVAL_LIMIT)
        self.assertEqual(len(maximum_matches), MAX_RETRIEVAL_LIMIT)
        self.assertTrue(
            all(
                match.memory in all_items[:CANDIDATE_POOL_SIZE]
                for match in maximum_matches
            )
        )
        self.assertTrue(
            all(call[2] == CANDIDATE_POOL_SIZE for call in self.backend.calls)
        )

    def test_invalid_limit_is_rejected_before_either_source_runs(self) -> None:
        for value in (True, False, 0, -1, 6, 1.5, None):
            with self.subTest(value=value):
                with self.assertRaises(MemoryValidationError):
                    self.retriever.retrieve("valid query", limit=value)
        self.assertEqual(self.backend.calls, [])

    def test_semantic_validation_is_authoritative_and_stops_lexical_work(self) -> None:
        error = MemoryValidationError("invalid semantic query")
        self.backend.semantic_error = error

        with self.assertRaises(MemoryValidationError) as raised:
            self.retriever.retrieve("invalid")

        self.assertIs(raised.exception, error)
        self.assertEqual(
            self.backend.calls,
            [("semantic", "invalid", CANDIDATE_POOL_SIZE)],
        )

    def test_lexical_validation_failure_degrades_to_semantic_only(self) -> None:
        item = memory(1)
        self.backend.semantic_results = (SemanticMatch(item, 0.8),)
        cases = (
            ("🙂🙃", "search query must contain a letter or number"),
            (
                "x" * 201,
                "search query cannot exceed 200 characters",
            ),
            (
                " ".join(f"term{number}" for number in range(17)),
                "search query cannot exceed 16 unique terms",
            ),
        )
        for query, message in cases:
            with self.subTest(query=query):
                self.backend.keyword_error = MemoryValidationError(message)
                matches = self.retriever.retrieve(query)
                self.assertEqual([match.memory for match in matches], [item])
                self.assertEqual(matches[0].sources, ("semantic",))

    def test_operational_errors_from_either_source_are_propagated(self) -> None:
        semantic_error = MemoryStoreError("semantic index incomplete")
        self.backend.semantic_error = semantic_error
        with self.assertRaises(MemoryStoreError) as raised:
            self.retriever.retrieve("question")
        self.assertIs(raised.exception, semantic_error)
        self.assertEqual(len(self.backend.calls), 1)

        backend = FakeMemorySearch()
        backend.keyword_error = MemoryStoreError("database unavailable")
        retriever = HybridRetriever(backend)
        with self.assertRaises(MemoryStoreError) as raised:
            retriever.retrieve("question")
        self.assertIs(raised.exception, backend.keyword_error)
        self.assertEqual(
            backend.calls,
            [
                ("semantic", "question", CANDIDATE_POOL_SIZE),
                ("keyword", "question", CANDIDATE_POOL_SIZE),
            ],
        )

    def test_keyword_only_results_require_a_successful_semantic_leg(self) -> None:
        item = memory(1)
        self.backend.semantic_results = ()
        self.backend.keyword_results = (KeywordMatch(item, -1.25),)

        matches = self.retriever.retrieve("exact name")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].memory, item)
        self.assertEqual(matches[0].sources, ("keyword",))
        self.assertIsNone(matches[0].semantic_score)
        self.assertEqual(matches[0].keyword_rank, -1.25)

    def test_duplicate_source_rows_use_first_position_only(self) -> None:
        item = memory(1)
        self.backend.semantic_results = (
            SemanticMatch(item, 0.9),
            SemanticMatch(item, 0.1),
        )
        self.backend.keyword_results = (
            KeywordMatch(item, -4.0),
            KeywordMatch(item, -20.0),
        )

        matches = self.retriever.retrieve("duplicate")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].semantic_position, 1)
        self.assertEqual(matches[0].semantic_score, 0.9)
        self.assertEqual(matches[0].keyword_position, 1)
        self.assertEqual(matches[0].keyword_rank, -4.0)
        self.assertAlmostEqual(matches[0].fused_score, 2.0 / (RRF_K + 1))

    def test_same_id_with_different_payload_fails_closed(self) -> None:
        original = memory(1, "Original text.")
        changed = replace(original, canonical_text="Changed text.")
        self.backend.semantic_results = (SemanticMatch(original, 0.9),)
        self.backend.keyword_results = (KeywordMatch(changed, -1.0),)

        with self.assertRaisesRegex(RetrievalError, "changed between"):
            self.retriever.retrieve("race")

    def test_malformed_results_and_nonfinite_diagnostics_fail_closed(self) -> None:
        item = memory(1)
        cases = (
            ("semantic_results", None),
            ("semantic_results", (object(),)),
            ("semantic_results", (SemanticMatch(item, math.nan),)),
            ("semantic_results", (SemanticMatch(item, math.inf),)),
            ("keyword_results", (KeywordMatch(item, math.nan),)),
            ("keyword_results", (KeywordMatch(item, math.inf),)),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                backend = FakeMemorySearch()
                setattr(backend, field, value)
                with self.assertRaises(RetrievalError):
                    HybridRetriever(backend).retrieve("malformed")

    def test_rrf_order_is_stable_across_repeated_calls(self) -> None:
        items = (memory(3), memory(2), memory(1))
        self.backend.semantic_results = tuple(
            SemanticMatch(item, 0.5) for item in items
        )
        self.backend.keyword_results = tuple(
            KeywordMatch(item, -1.0) for item in reversed(items)
        )

        expected = [memory(1).id, memory(3).id, memory(2).id]
        for _ in range(5):
            matches = self.retriever.retrieve("stable")
            self.assertEqual([match.memory.id for match in matches], expected)

    def test_is_current_delegates_full_items_and_propagates_status(self) -> None:
        first = memory(1)
        second = memory(2)
        matches = (
            HybridMatch(first, 0.1, None, None, 0.9, 1),
            HybridMatch(second, 0.09, -1.0, 1, None, None),
        )

        self.assertTrue(self.retriever.is_current(matches))
        self.assertEqual(self.backend.snapshot_calls, [(first, second)])

        self.backend.snapshot_result = False
        self.assertFalse(self.retriever.is_current(matches))
        error = MemoryStoreError("snapshot unavailable")
        self.backend.snapshot_error = error
        with self.assertRaises(MemoryStoreError) as raised:
            self.retriever.is_current(matches)
        self.assertIs(raised.exception, error)

    def test_is_current_empty_and_invalid_inputs_fail_closed(self) -> None:
        self.assertTrue(self.retriever.is_current(()))
        self.assertEqual(self.backend.snapshot_calls, [])

        item = memory(1)
        match = HybridMatch(item, 0.1, None, None, 0.9, 1)
        invalid_memory = HybridMatch(object(), 0.1, None, None, 0.9, 1)
        too_many = tuple(match for _ in range(MAX_RETRIEVAL_LIMIT + 1))
        for invalid in (
            None,
            "bad",
            (object(),),
            (invalid_memory,),
            (match, match),
            too_many,
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(RetrievalError):
                    self.retriever.is_current(invalid)
        self.assertEqual(self.backend.snapshot_calls, [])

    def test_invalid_backend_snapshot_status_fails_closed(self) -> None:
        item = memory(1)
        match = HybridMatch(item, 0.1, None, None, 0.9, 1)
        self.backend.snapshot_result = 1

        with self.assertRaisesRegex(RetrievalError, "snapshot status"):
            self.retriever.is_current((match,))


if __name__ == "__main__":
    unittest.main()
