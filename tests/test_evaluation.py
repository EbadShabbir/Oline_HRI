import copy
from dataclasses import replace
from datetime import date, datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oline_hri.evaluation import (
    ANNOTATION_STATUS,
    DEFAULT_MANIFEST_PATH,
    MAX_MANIFEST_BYTES,
    EvaluationReplayError,
    EvaluationValidationError,
    emit_prompts,
    load_evaluation_suite,
    materialize_memory_store,
    prompt_records,
)


REQUIRED_CATEGORIES = {
    "general",
    "direct_fact",
    "preference",
    "temporal",
    "correction",
    "contradiction",
    "recency",
    "expiration",
    "forgetting",
    "absent",
    "privacy",
    "synthesis",
}
EXPECTED_ROUTES = {
    (False, "small"),
    (False, "large"),
    (True, "small"),
    (True, "large"),
}

OLD_TEA_ID = "mem_00000000000000000000000000000002"
EXPIRED_NOTEBOOK_ID = "mem_00000000000000000000000000000006"
NEW_TEA_ID = "mem_00000000000000000000000000000009"
FORGOTTEN_STAY_HOME_ID = "mem_0000000000000000000000000000000a"
UNKNOWN_MEMORY_ID = "mem_ffffffffffffffffffffffffffffffff"
VERSIONED_MANIFEST_PATH = DEFAULT_MANIFEST_PATH.with_name(
    "fictional_seven_day_v1_1.json"
)
VERSIONED_PACKAGED_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "oline_hri"
    / "fictional_seven_day_v1_1.json"
)


def _manifest_data() -> dict[str, object]:
    return json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))


class EvaluationManifestTests(unittest.TestCase):
    def _load_mutation(self, mutate) -> None:
        data = copy.deepcopy(_manifest_data())
        mutate(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(
                json.dumps(data, ensure_ascii=True),
                encoding="utf-8",
            )
            load_evaluation_suite(path)

    def _assert_mutation_rejected(self, mutate) -> None:
        with self.assertRaises(EvaluationValidationError):
            self._load_mutation(mutate)

    def test_default_manifest_is_explicitly_fictional_and_has_full_coverage(
        self,
    ) -> None:
        suite = load_evaluation_suite()

        self.assertEqual(DEFAULT_MANIFEST_PATH.name, "fictional_seven_day_v1.json")
        self.assertTrue(suite.fictional)
        self.assertFalse(suite.contains_human_participant_data)
        self.assertEqual(suite.annotation_status, ANNOTATION_STATUS)
        self.assertIn("fictional", suite.title.lower())
        self.assertIn("fictional", suite.description.lower())

        start = date.fromisoformat(suite.week_start)
        end = date.fromisoformat(suite.week_end)
        self.assertEqual((end - start).days, 6)
        event_dates = {
            datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")).date()
            for event in suite.memory_events
        }
        evaluation_date = datetime.fromisoformat(
            suite.evaluation_at.replace("Z", "+00:00")
        ).date()
        self.assertEqual(len(event_dates), 7)
        self.assertEqual(min(event_dates), start)
        self.assertEqual(max(event_dates), end)
        self.assertEqual(evaluation_date, end)
        self.assertEqual({event.day for event in suite.memory_events}, set(range(1, 8)))

        self.assertEqual({case.category for case in suite.cases}, REQUIRED_CATEGORIES)
        categories_by_case = {case.id: case.category for case in suite.cases}
        self.assertEqual(categories_by_case["memory_direct_fact"], "direct_fact")
        self.assertEqual(categories_by_case["memory_routine"], "preference")
        self.assertEqual(
            {
                (
                    case.expected_route.memory_required,
                    case.expected_route.model_size,
                )
                for case in suite.cases
            },
            EXPECTED_ROUTES,
        )
        self.assertTrue(all("router" in case.tags for case in suite.cases))
        self.assertTrue(
            all(
                ("rag" in case.tags) == case.expected_route.memory_required
                for case in suite.cases
            )
        )
        self.assertTrue(
            all(not topic.value_included for topic in suite.withheld_topics)
        )
        self.assertEqual(
            {topic.category for topic in suite.withheld_topics},
            {
                "prohibited_secret",
                "third_party_private_information",
                "unconfirmed_inference",
            },
        )
        privacy_tags = {
            tag
            for case in suite.cases
            if case.category == "privacy"
            for tag in case.tags
        }
        self.assertTrue(
            {
                "prohibited_secret",
                "third_party_private_information",
                "unconfirmed_inference",
            }
            <= privacy_tags
        )

        cases_by_id = {case.id: case for case in suite.cases}
        recency = cases_by_id["memory_large_recency"]
        self.assertEqual(recency.category, "recency")
        self.assertEqual(
            recency.retrieval_gold.top_id,
            "mem_0000000000000000000000000000000b",
        )
        self.assertIn(
            "mem_00000000000000000000000000000001",
            recency.retrieval_gold.required_ids,
        )
        self.assertIn(
            "mem_0000000000000000000000000000000b",
            recency.retrieval_gold.required_ids,
        )

    def test_packaged_manifest_is_available_without_source_tree(self) -> None:
        source_suite = load_evaluation_suite()
        with patch(
            "oline_hri.evaluation.DEFAULT_MANIFEST_PATH",
            Path("/missing/fictional_seven_day_v1.json"),
        ):
            packaged_suite = load_evaluation_suite()

        self.assertEqual(packaged_suite, source_suite)

    def test_v1_1_manifest_copies_match_and_suite_id_is_versioned(self) -> None:
        self.assertEqual(
            VERSIONED_PACKAGED_MANIFEST_PATH.read_bytes(),
            VERSIONED_MANIFEST_PATH.read_bytes(),
        )
        suite = load_evaluation_suite(VERSIONED_MANIFEST_PATH)
        self.assertEqual(
            suite.suite_id,
            "oline_hri_fictional_seven_day_v1_1",
        )

    def test_v1_1_temporal_prompt_requests_undisclosed_new_value(self) -> None:
        suite = load_evaluation_suite(VERSIONED_MANIFEST_PATH)
        temporal = next(
            case for case in suite.cases if case.id == "memory_large_temporal"
        )
        prompt = temporal.prompt.casefold()
        self.assertIn("what it changed to", prompt)
        self.assertNotIn("ginger", prompt)
        self.assertIn(
            "tea changed to ginger on friday",
            {claim.casefold() for claim in temporal.answer_rubric.required_claims},
        )

    def test_prompt_jsonl_is_deterministic_canonical_and_track_filtered(self) -> None:
        suite = load_evaluation_suite()

        all_output = emit_prompts(suite)
        self.assertEqual(all_output, emit_prompts(suite, track="all"))
        self.assertTrue(all_output.endswith("\n"))
        all_lines = all_output.splitlines()
        all_records = tuple(json.loads(line) for line in all_lines)
        self.assertEqual(all_records, prompt_records(suite))
        self.assertEqual(
            [record["case_id"] for record in all_records],
            [case.id for case in suite.cases],
        )
        expected_fields = {
            "schema_version",
            "suite_id",
            "fictional",
            "contains_human_participant_data",
            "annotation_status",
            "profile_id",
            "evaluation_at",
            "case_id",
            "category",
            "prompt",
            "expected_route",
            "retrieval_gold",
            "answer_rubric",
            "tags",
        }
        cases_by_id = {case.id: case for case in suite.cases}
        for line, record in zip(all_lines, all_records):
            case = cases_by_id[record["case_id"]]
            self.assertEqual(set(record), expected_fields)
            self.assertEqual(record["schema_version"], suite.schema_version)
            self.assertEqual(record["suite_id"], suite.suite_id)
            self.assertIs(record["fictional"], True)
            self.assertIs(record["contains_human_participant_data"], False)
            self.assertEqual(record["annotation_status"], suite.annotation_status)
            self.assertEqual(record["profile_id"], suite.profile_id)
            self.assertEqual(record["evaluation_at"], suite.evaluation_at)
            self.assertEqual(record["prompt"], case.prompt)
            self.assertEqual(record["category"], case.category)
            self.assertEqual(
                line,
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )

        for track in ("router", "rag"):
            expected = tuple(
                case.id for case in suite.cases if track in case.tags
            )
            output = emit_prompts(suite, track=track)
            records = tuple(json.loads(line) for line in output.splitlines())
            self.assertEqual(tuple(record["case_id"] for record in records), expected)
            self.assertEqual(records, prompt_records(suite, track=track))

        self.assertEqual(len(all_records), 30)
        self.assertEqual(len(prompt_records(suite, track="router")), 30)
        self.assertEqual(len(prompt_records(suite, track="rag")), 16)
        with self.assertRaises(EvaluationValidationError):
            emit_prompts(suite, track="performance")

    def test_unknown_and_missing_fields_are_rejected_at_each_level(self) -> None:
        mutations = {
            "unknown top-level": lambda data: data.__setitem__("score", 1),
            "missing top-level": lambda data: data.pop("title"),
            "unknown event": lambda data: data["memory_events"][0].__setitem__(
                "note", "unexpected"
            ),
            "missing record": lambda data: data["memory_events"][0]["record"].pop(
                "kind"
            ),
            "unknown case": lambda data: data["cases"][0].__setitem__(
                "latency_ms", 1
            ),
            "missing rubric": lambda data: data["cases"][0][
                "answer_rubric"
            ].pop("reference_answer"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                self._assert_mutation_rejected(mutate)

    def test_duplicate_json_fields_and_semantic_identifiers_are_rejected(self) -> None:
        raw = DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8")
        duplicate_raw = raw.replace(
            '  "schema_version": 1,',
            '  "schema_version": 1,\n  "schema_version": 1,',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-key.json"
            path.write_text(duplicate_raw, encoding="utf-8")
            with self.assertRaises(EvaluationValidationError):
                load_evaluation_suite(path)

        def duplicate_event_id(data) -> None:
            data["memory_events"][1]["id"] = data["memory_events"][0]["id"]

        def duplicate_case_id(data) -> None:
            data["cases"][1]["id"] = data["cases"][0]["id"]

        def duplicate_gold_id(data) -> None:
            case = next(
                item for item in data["cases"] if item["retrieval_gold"]["relevant_ids"]
            )
            relevant = case["retrieval_gold"]["relevant_ids"]
            relevant.append(relevant[0])

        for label, mutate in (
            ("event ID", duplicate_event_id),
            ("case ID", duplicate_case_id),
            ("gold ID", duplicate_gold_id),
        ):
            with self.subTest(label=label):
                self._assert_mutation_rejected(mutate)

    def test_wrong_types_and_malformed_identifiers_are_rejected(self) -> None:
        mutations = {
            "boolean metadata": lambda data: data.__setitem__("fictional", 1),
            "boolean day": lambda data: data["memory_events"][0].__setitem__(
                "day", True
            ),
            "numeric confidence": lambda data: data["memory_events"][0][
                "record"
            ].__setitem__("confidence", "1.0"),
            "event identifier": lambda data: data["memory_events"][0].__setitem__(
                "id", "Event 1"
            ),
            "memory identifier": lambda data: data["memory_events"][0][
                "record"
            ].__setitem__("id", "memory-1"),
            "case identifier": lambda data: data["cases"][0].__setitem__(
                "id", "Case 1"
            ),
            "surrogate prompt": lambda data: data["cases"][0].__setitem__(
                "prompt", "bad\ud800prompt"
            ),
            "line separator prompt": lambda data: data["cases"][0].__setitem__(
                "prompt", "one\u2028two"
            ),
            "huge confidence": lambda data: data["memory_events"][0][
                "record"
            ].__setitem__("confidence", 10**400),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                self._assert_mutation_rejected(mutate)

    def test_oversized_nonregular_and_huge_number_manifests_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (MAX_MANIFEST_BYTES + 1))
            with self.assertRaises(EvaluationValidationError):
                load_evaluation_suite(oversized)

            fifo = root / "manifest.fifo"
            os.mkfifo(fifo)
            with self.assertRaises(EvaluationValidationError):
                load_evaluation_suite(fifo)

            huge_integer = root / "huge-integer.json"
            raw = DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8")
            raw = raw.replace(
                '"schema_version": 1',
                f'"schema_version": {"9" * 10_000}',
                1,
            )
            huge_integer.write_text(raw, encoding="utf-8")
            with self.assertRaises(EvaluationValidationError):
                load_evaluation_suite(huge_integer)

    def test_noncanonical_mismatched_and_out_of_order_timestamps_are_rejected(
        self,
    ) -> None:
        def noncanonical_timestamp(data) -> None:
            data["memory_events"][0]["timestamp"] = "2026-08-03T09:00:00Z"

        def record_timestamp_mismatch(data) -> None:
            data["memory_events"][0]["record"][
                "created_at"
            ] = "2026-08-03T09:01:00.000000Z"

        def reverse_events(data) -> None:
            data["memory_events"][0], data["memory_events"][1] = (
                data["memory_events"][1],
                data["memory_events"][0],
            )

        def duplicate_event_timestamp(data) -> None:
            first_timestamp = data["memory_events"][0]["timestamp"]
            event = data["memory_events"][1]
            event["timestamp"] = first_timestamp
            event["record"]["valid_from"] = first_timestamp
            event["record"]["created_at"] = first_timestamp
            event["record"]["updated_at"] = first_timestamp

        def evaluation_after_week(data) -> None:
            data["evaluation_at"] = "2026-08-10T20:00:00.000000Z"

        for label, mutate in (
            ("noncanonical", noncanonical_timestamp),
            ("record mismatch", record_timestamp_mismatch),
            ("chronology", reverse_events),
            ("strict chronology", duplicate_event_timestamp),
            ("evaluation date", evaluation_after_week),
        ):
            with self.subTest(label=label):
                self._assert_mutation_rejected(mutate)

    def test_invalid_correction_forget_and_expiration_lifecycle_is_rejected(
        self,
    ) -> None:
        def unknown_correction_target(data) -> None:
            correction = next(
                event
                for event in data["memory_events"]
                if event["operation"] == "correct"
            )
            correction["target_id"] = UNKNOWN_MEMORY_ID
            correction["record"]["supersedes_id"] = UNKNOWN_MEMORY_ID

        def wrong_correction_lineage(data) -> None:
            correction = next(
                event
                for event in data["memory_events"]
                if event["operation"] == "correct"
            )
            correction["record"]["supersedes_id"] = (
                "mem_00000000000000000000000000000001"
            )

        def unknown_forget_target(data) -> None:
            forgotten = next(
                event
                for event in data["memory_events"]
                if event["operation"] == "forget"
            )
            forgotten["target_id"] = UNKNOWN_MEMORY_ID

        def invalid_expiration_range(data) -> None:
            record = data["memory_events"][0]["record"]
            record["valid_until"] = "2026-08-03T08:59:00.000000Z"

        def retention_precedes_expiration(data) -> None:
            record = data["memory_events"][0]["record"]
            record["valid_until"] = "2026-08-05T09:00:00.000000Z"
            record["retention_until"] = "2026-08-04T09:00:00.000000Z"

        def expired_forget_target(data) -> None:
            forgotten = next(
                event
                for event in data["memory_events"]
                if event["operation"] == "forget"
            )
            target = next(
                event["record"]
                for event in data["memory_events"]
                if event.get("record", {}).get("id") == forgotten["target_id"]
            )
            target["valid_until"] = forgotten["timestamp"]

        for label, mutate in (
            ("correction target", unknown_correction_target),
            ("correction lineage", wrong_correction_lineage),
            ("forget target", unknown_forget_target),
            ("expiration range", invalid_expiration_range),
            ("retention before expiration", retention_precedes_expiration),
            ("forget eligibility", expired_forget_target),
        ):
            with self.subTest(label=label):
                self._assert_mutation_rejected(mutate)

    def test_inconsistent_retrieval_gold_is_rejected(self) -> None:
        def required_not_relevant(data) -> None:
            case = next(
                item
                for item in data["cases"]
                if item["answer_rubric"]["mode"] == "supported"
                and item["expected_route"]["memory_required"]
            )
            case["retrieval_gold"]["required_ids"] = [UNKNOWN_MEMORY_ID]

        def relevant_and_forbidden(data) -> None:
            case = next(
                item for item in data["cases"] if item["retrieval_gold"]["relevant_ids"]
            )
            identifier = case["retrieval_gold"]["relevant_ids"][0]
            case["retrieval_gold"]["forbidden_ids"].append(identifier)

        def top_not_relevant(data) -> None:
            case = next(
                item for item in data["cases"] if item["retrieval_gold"]["relevant_ids"]
            )
            case["retrieval_gold"]["top_id"] = UNKNOWN_MEMORY_ID

        def no_memory_has_gold(data) -> None:
            case = next(
                item
                for item in data["cases"]
                if not item["expected_route"]["memory_required"]
            )
            case["retrieval_gold"]["forbidden_ids"] = [OLD_TEA_ID]

        def current_memory_is_forbidden(data) -> None:
            case = next(
                item
                for item in data["cases"]
                if item["retrieval_gold"]["relevant_ids"]
                and not item["retrieval_gold"]["forbidden_ids"]
            )
            case["retrieval_gold"]["forbidden_ids"] = [NEW_TEA_ID]

        for label, mutate in (
            ("required subset", required_not_relevant),
            ("disjoint gold", relevant_and_forbidden),
            ("top relevant", top_not_relevant),
            ("no-memory gold", no_memory_has_gold),
            ("retrievable forbidden ID", current_memory_is_forbidden),
        ):
            with self.subTest(label=label):
                self._assert_mutation_rejected(mutate)

    def test_inconsistent_answer_rubrics_are_rejected(self) -> None:
        def invalid_mode(data) -> None:
            data["cases"][0]["answer_rubric"]["mode"] = "pass"

        def supported_without_citation(data) -> None:
            case = next(
                item
                for item in data["cases"]
                if item["answer_rubric"]["mode"] == "supported"
                and item["expected_route"]["memory_required"]
            )
            case["answer_rubric"]["required_citation_ids"] = []

        def abstention_with_evidence(data) -> None:
            case = next(
                item
                for item in data["cases"]
                if item["answer_rubric"]["mode"] == "abstain"
            )
            case["retrieval_gold"]["relevant_ids"] = [NEW_TEA_ID]

        def uncertain_without_evidence(data) -> None:
            case = next(
                item
                for item in data["cases"]
                if item["answer_rubric"]["mode"] == "uncertain"
            )
            case["retrieval_gold"]["relevant_ids"] = []
            case["retrieval_gold"]["required_ids"] = []
            case["answer_rubric"]["required_citation_ids"] = []

        for label, mutate in (
            ("mode", invalid_mode),
            ("supported evidence", supported_without_citation),
            ("abstention evidence", abstention_with_evidence),
            ("uncertain evidence", uncertain_without_evidence),
        ):
            with self.subTest(label=label):
                self._assert_mutation_rejected(mutate)

    def test_week_operation_route_category_and_rubric_coverage_are_required(
        self,
    ) -> None:
        def omit_day_seven(data) -> None:
            data["memory_events"] = [
                event for event in data["memory_events"] if event["day"] != 7
            ]

        def omit_forget(data) -> None:
            data["memory_events"] = [
                event
                for event in data["memory_events"]
                if event["operation"] != "forget"
            ]

        def omit_route(data) -> None:
            data["cases"] = [
                case
                for case in data["cases"]
                if not (
                    case["expected_route"]["memory_required"] is False
                    and case["expected_route"]["model_size"] == "large"
                )
            ]

        def omit_category(data) -> None:
            data["cases"] = [
                case for case in data["cases"] if case["category"] != "privacy"
            ]

        def omit_abstention(data) -> None:
            for case in data["cases"]:
                if case["answer_rubric"]["mode"] == "abstain":
                    case["answer_rubric"]["mode"] = "uncertain"

        def omit_withheld_category(data) -> None:
            data["withheld_topics"].pop()

        def omit_unconfirmed_inference_case(data) -> None:
            data["cases"] = [
                case
                for case in data["cases"]
                if case["id"] != "privacy_unconfirmed_inference"
            ]

        def make_older_recency_record_top(data) -> None:
            case = next(
                case
                for case in data["cases"]
                if case["id"] == "memory_large_recency"
            )
            case["retrieval_gold"]["top_id"] = (
                "mem_00000000000000000000000000000001"
            )

        for label, mutate in (
            ("seven days", omit_day_seven),
            ("lifecycle operations", omit_forget),
            ("four routes", omit_route),
            ("scenario categories", omit_category),
            ("abstention rubric", omit_abstention),
            ("withheld privacy categories", omit_withheld_category),
            ("unconfirmed inference prompt", omit_unconfirmed_inference_case),
            ("newest recency top", make_older_recency_record_top),
        ):
            with self.subTest(label=label):
                self._assert_mutation_rejected(mutate)


class EvaluationMaterializationTests(unittest.TestCase):
    def test_public_helpers_revalidate_constructed_suite_before_writing(self) -> None:
        invalid_suite = replace(load_evaluation_suite(), memory_events=())
        with self.assertRaises(EvaluationValidationError):
            prompt_records(invalid_suite)

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "invalid.sqlite3"
            with self.assertRaises(EvaluationValidationError):
                materialize_memory_store(invalid_suite, database)
            self.assertFalse(database.exists())

    def test_materialization_replays_exact_final_state_in_a_new_database(self) -> None:
        suite = load_evaluation_suite()
        source_records = {
            event.record.id: event.record
            for event in suite.memory_events
            if event.record is not None
        }
        correction = next(
            event for event in suite.memory_events if event.operation == "correct"
        )
        self.assertEqual(correction.target_id, OLD_TEA_ID)
        self.assertEqual(correction.record.id, NEW_TEA_ID)

        expected = dict(source_records)
        expected.pop(FORGOTTEN_STAY_HOME_ID)
        expected[OLD_TEA_ID] = replace(
            expected[OLD_TEA_ID],
            status="superseded",
            valid_until=correction.timestamp,
            updated_at=correction.timestamp,
        )

        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "isolated"
            private.mkdir(mode=0o700)
            database = private / "evaluation.sqlite3"
            self.assertFalse(database.exists())

            store = materialize_memory_store(suite, database)

            self.assertTrue(database.is_file())
            self.assertEqual(store.database_path, database)
            actual = {
                item.id: item
                for item in store.list_memories(include_inactive=True)
            }
            self.assertEqual(actual, expected)
            self.assertEqual(actual[OLD_TEA_ID].status, "superseded")
            self.assertEqual(actual[NEW_TEA_ID].supersedes_id, OLD_TEA_ID)
            self.assertNotIn(FORGOTTEN_STAY_HOME_ID, actual)

            self.assertEqual(store.search_keywords("mint tea"), ())
            self.assertEqual(
                store.search_keywords("ginger tea")[0].memory.id,
                NEW_TEA_ID,
            )
            self.assertEqual(store.search_keywords("blue notebook"), ())
            self.assertEqual(store.search_keywords("stay home"), ())
            self.assertFalse(
                store.retrieval_snapshot_is_current((actual[OLD_TEA_ID],))
            )
            self.assertFalse(
                store.retrieval_snapshot_is_current(
                    (actual[EXPIRED_NOTEBOOK_ID],)
                )
            )
            self.assertTrue(
                store.retrieval_snapshot_is_current((actual[NEW_TEA_ID],))
            )

    def test_materialization_rejects_existing_and_relative_database_paths(self) -> None:
        suite = load_evaluation_suite()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "existing.sqlite3"
            sentinel = b"do not replace"
            database.write_bytes(sentinel)

            with self.assertRaises(EvaluationReplayError):
                materialize_memory_store(suite, database)

            self.assertEqual(database.read_bytes(), sentinel)

        with self.assertRaises(EvaluationReplayError):
            materialize_memory_store(suite, Path("relative.sqlite3"))
        for unsafe in (Path("/"), "/tmp/bad\x00name.sqlite3", 7):
            with self.subTest(unsafe=repr(unsafe)):
                with self.assertRaises(EvaluationReplayError):
                    materialize_memory_store(suite, unsafe)

    def test_materialization_preserves_preexisting_sidecar_files(self) -> None:
        suite = load_evaluation_suite()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "evaluation.sqlite3"
            sidecar = Path(f"{database}-wal")
            sentinel = b"not created by the evaluation replay"
            sidecar.write_bytes(sentinel)

            with self.assertRaises(EvaluationReplayError):
                materialize_memory_store(suite, database)

            self.assertFalse(database.exists())
            self.assertEqual(sidecar.read_bytes(), sentinel)

    def test_materialization_rejects_shared_or_symlinked_parent(self) -> None:
        suite = load_evaluation_suite()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = root / "shared"
            shared.mkdir(mode=0o770)
            shared.chmod(0o770)
            nested_private = shared / "private"
            nested_private.mkdir(mode=0o700)
            with self.assertRaises(EvaluationReplayError):
                materialize_memory_store(
                    suite,
                    nested_private / "evaluation.sqlite3",
                )

            private = root / "private"
            private.mkdir(mode=0o700)
            linked = root / "linked"
            linked.symlink_to(private, target_is_directory=True)
            with self.assertRaises(EvaluationReplayError):
                materialize_memory_store(
                    suite,
                    linked / "new" / "evaluation.sqlite3",
                )

            missing = root / "missing"
            with self.assertRaises(EvaluationReplayError):
                materialize_memory_store(
                    suite,
                    missing / "evaluation.sqlite3",
                )

            self.assertFalse((nested_private / "evaluation.sqlite3").exists())
            self.assertFalse((private / "evaluation.sqlite3").exists())
            self.assertFalse((private / "new").exists())
            self.assertFalse(missing.exists())
            self.assertFalse((private / "evaluation.sqlite3").exists())

    def test_interrupt_cleans_up_database_created_by_replay(self) -> None:
        suite = load_evaluation_suite()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "evaluation.sqlite3"
            with patch(
                "oline_hri.evaluation.MemoryStore.remember",
                side_effect=KeyboardInterrupt,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    materialize_memory_store(suite, database)

            self.assertFalse(database.exists())

    def test_interrupt_is_preserved_when_safe_cleanup_is_incomplete(self) -> None:
        suite = load_evaluation_suite()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "evaluation.sqlite3"
            sidecar = Path(f"{database}-journal")
            sentinel = b"concurrent sidecar not owned by replay"

            def interrupt_with_sidecar(*args, **kwargs):
                sidecar.write_bytes(sentinel)
                raise KeyboardInterrupt

            with patch(
                "oline_hri.evaluation.MemoryStore.remember",
                side_effect=interrupt_with_sidecar,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    materialize_memory_store(suite, database)

            self.assertTrue(database.exists())
            self.assertEqual(sidecar.read_bytes(), sentinel)

    def test_failed_replay_does_not_delete_a_replacement_file(self) -> None:
        suite = load_evaluation_suite()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "evaluation.sqlite3"
            sentinel = b"replacement not owned by replay"

            def replace_database(*args, **kwargs):
                database.unlink()
                database.write_bytes(sentinel)
                raise RuntimeError("injected replay failure")

            with patch(
                "oline_hri.evaluation.MemoryStore.remember",
                side_effect=replace_database,
            ):
                with self.assertRaisesRegex(
                    EvaluationReplayError,
                    "cleanup was incomplete",
                ):
                    materialize_memory_store(suite, database)

            self.assertEqual(database.read_bytes(), sentinel)

    def test_failed_replay_does_not_delete_an_ambiguous_sidecar(self) -> None:
        suite = load_evaluation_suite()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "evaluation.sqlite3"
            sidecar = Path(f"{database}-journal")
            sentinel = b"concurrent sidecar not owned by replay"

            def create_sidecar(*args, **kwargs):
                sidecar.write_bytes(sentinel)
                raise RuntimeError("injected replay failure")

            with patch(
                "oline_hri.evaluation.MemoryStore.remember",
                side_effect=create_sidecar,
            ):
                with self.assertRaisesRegex(
                    EvaluationReplayError,
                    "cleanup was incomplete",
                ):
                    materialize_memory_store(suite, database)

            self.assertTrue(database.exists())
            self.assertEqual(sidecar.read_bytes(), sentinel)


if __name__ == "__main__":
    unittest.main()
