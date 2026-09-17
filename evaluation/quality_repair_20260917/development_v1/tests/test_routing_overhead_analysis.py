"""Synthetic accounting checks: none of these timings are model measurements."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_routing_overhead as analysis


def span(eid, parent, name, start, end):
    return dict(id=eid, parent_id=parent, name=name, start_ns=start, end_ns=end, wall_ns=end-start)


def request():
    return dict(arm="adaptive", start_ns=0, end_ns=100, wall_ns=100, events=[
        span(1, None, "complete_request", 0, 100), span(2, 1, "routing", 0, 40),
        span(3, 2, "deterministic_routing", 0, 10), span(4, 2, "memory_classifier", 10, 40),
        span(5, 4, "backend_chat", 10, 40), span(6, 1, "answer_generation", 40, 90),
        span(7, 6, "model_transition", 40, 50), span(8, 7, "unload_request", 40, 44),
        span(9, 7, "eviction_verification", 44, 50), span(10, 6, "backend_chat", 50, 90),
        span(11, 1, "validation", 90, 95)])


class SpanAccountingTests(unittest.TestCase):
    def test_nested_loading_is_never_added_to_wall(self):
        row = request()
        row["events"][9]["attributes"] = {"backend_load_duration_ns": 25, "backend_total_duration_ns": 39}
        actual = analysis.account_spans(row)
        self.assertEqual(actual, dict(deterministic_routing_and_bookkeeping=10, memory_classifier=30,
                                    eviction=10, answer_generation=40, validation=5, other_instrumented=5))
        self.assertEqual(sum(actual.values()), 100)

    def test_sibling_overlap_and_wrong_parent_are_rejected(self):
        for mutation in (lambda row: row["events"].append(span(12, 1, "retrieval", 70, 90)),
                         lambda row: row["events"].append(span(12, 3, "backend_chat", 10, 20)),
                         lambda row: row["events"].append(span(12, 1, "validation", 95, 101))):
            row = request(); mutation(row)
            with self.assertRaises(ValueError): analysis.account_spans(row)

    def test_cyclic_duplicate_and_changed_wall_are_rejected(self):
        row = request(); row["events"].append(deepcopy(row["events"][0]))
        with self.assertRaises(ValueError): analysis.account_spans(row)
        row = request(); row["events"][0]["parent_id"] = 1
        with self.assertRaises(ValueError): analysis.account_spans(row)
        row = request(); row["wall_ns"] = 101
        with self.assertRaises(ValueError): analysis.account_spans(row)

    def test_unaccounted_spans_and_interval_union(self):
        row = dict(start_ns=0, end_ns=100, wall_ns=100, events=[span(1, None, "retrieval", 10, 30)])
        self.assertEqual(analysis.account_spans(row), dict(unaccounted=80, retrieval=20))
        self.assertEqual(analysis.union_ns([(10, 30), (20, 40), (50, 70)]), 50)

    def test_true_fixed_and_diagnostic_replay_calls_are_enforced(self):
        for arm in ("small", "large", "replay"):
            bad = dict(arm=arm, calls=[dict(requested_model=analysis.LARGE if arm == "small" else analysis.SMALL,
                                          purpose="memory_selector")])
            with self.assertRaises(ValueError): analysis.audit_calls(bad)
        analysis.audit_calls(dict(arm="large", calls=[dict(requested_model=analysis.LARGE, purpose="memory_selector")]))


class SummaryTests(unittest.TestCase):
    def test_paired_repetition_means_use_sequence_clusters(self):
        pairs = []
        for sequence, delta in (("a", 1), ("b", 9), ("c", 5)):
            for repetition in (1, 2, 3):
                pairs.append(dict(sequence_id=sequence, pattern="EEEE", comparator="large", repetition=repetition,
                                  adaptive_minus_comparator_seconds=delta))
        clusters, summaries = analysis.cluster_summary(pairs, resamples=100)
        self.assertEqual(len(clusters), 3)
        overall = next(row for row in summaries if row["comparator"] == "large" and row["pattern"] == "overall")
        self.assertEqual(overall["sequence_clusters"], 3)
        self.assertEqual(overall["complete_three_repetition_clusters"], 3)
        self.assertEqual(overall["mean_adaptive_minus_comparator_seconds"], 5)

    def test_incomplete_sequences_never_enter_paired_totals_and_duplicates_rejected(self):
        rows = [dict(sequence_id="a", pattern="DDEE", repetition=1, arm=arm, complete=True,
                     sequence_seconds=value, startup_seconds=1, request_seconds=value-1)
                for arm, value in (("small", 3), ("large", 9), ("adaptive", 7), ("replay", 5))]
        pairs = analysis.paired_sequences(rows)
        self.assertEqual({row["comparator"]: row["adaptive_minus_comparator_seconds"] for row in pairs},
                         dict(small=4, large=-2, replay=2))
        rows[1]["complete"] = False
        self.assertEqual(len(analysis.paired_sequences(rows)), 2)
        with self.assertRaises(ValueError): analysis.paired_sequences(rows + [rows[0]])

    def test_following_turn_and_return_to_small_are_actual_not_workload_labels(self):
        rows = []
        previous = []
        for index, model in enumerate((analysis.LARGE, analysis.LARGE, analysis.LARGE, analysis.SMALL, analysis.SMALL), 1):
            after = [dict(name=model, size=100, size_vram=75, digest="digest")]
            rows.append(dict(attempt_directory="test", id=f"q{index}", index=index, arm="adaptive",
                             wall_ns=100, api_ps_before=previous, api_ps_after=after, generation=dict(model=model)))
            previous = after
        turns = analysis.turn_table(rows)
        self.assertEqual([row["return_to_small"] for row in turns], [False, False, False, True, False])
        self.assertTrue(turns[-1]["following_small_return"])
        self.assertEqual(turns[0]["residency_condition"], "cold_start")
        self.assertEqual(turns[3]["residency_condition"], "model_switch")

    def test_blind_packet_has_no_model_or_timing_and_reviews_cover_every_attempt(self):
        raw = dict(attempt_directory="run", id="q1", index=1, arm="adaptive", sequence_id="s1", repetition=1,
                   prompt="What is the answer?", response=dict(speech="Four."), status="ok",
                   history_before=[], wall_ns=100, generation=dict(model=analysis.LARGE))
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            count = analysis.make_blind({}, [raw], directory / "blind")
            self.assertEqual(count, 1)
            packet = analysis.jsonl(directory / "blind/packet.jsonl")[0]
            self.assertFalse({"model", "arm", "wall_ns"} & packet.keys())
            review = dict(answer_id=packet["answer_id"], label="complete", rationale="Matches the rubric.")
            analysis.lines(directory / "reviews.jsonl", [review])
            _, quality = analysis.quality_join([raw], directory / "blind", [directory / "reviews.jsonl"])
            self.assertEqual(quality["systems"]["adaptive"]["correct"], 1)
            with self.assertRaises(ValueError):
                analysis.quality_join([dict(raw, status="error")], directory / "blind", [directory / "reviews.jsonl"])

    def test_load_preserves_incomplete_attempt_and_cold_startup_accounting(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); run = root / "run"; run.mkdir(); complete = run / "done"; complete.mkdir()
            workload = root / "workload.json"; analysis.write(workload, {})
            freeze = root / "freeze.json"; analysis.write(freeze, {"workload_sha256": sha256(workload.read_bytes()).hexdigest()})
            identity = dict(sequence_id="a", pattern="EEEE", arm="small", repetition=1)
            analysis.write(complete / "manifest.json", identity)
            analysis.write(complete / "startup.json", dict(wall_ns=10))
            rows = [dict(start_ns=100*i, end_ns=100*i+50, wall_ns=50, id=f"q{i}", index=i,
                         status="ok", events=[], calls=[]) for i in range(1, 5)]
            analysis.lines(complete / "observations.jsonl", rows)
            analysis.write(complete / "finish.json", dict(status="complete", startup_ns=10,
                           request_total_ns=200, sequence_total_ns=210))
            incomplete = run / "interrupted"; incomplete.mkdir()
            analysis.write(incomplete / "manifest.json", {**identity, "arm": "large"})
            analysis.lines(incomplete / "observations.jsonl", [{**rows[0], "status": "error"}])
            _, _, runs, observations, _, _, _, errors = analysis.load_inputs(run, workload, freeze)
            self.assertEqual(len(observations), 5)
            self.assertEqual(sum(row["complete"] for row in runs), 1)
            self.assertEqual(errors, [])
            analysis.write(complete / "finish.json", dict(status="complete", startup_ns=10,
                           request_total_ns=200, sequence_total_ns=220))
            *_, errors = analysis.load_inputs(run, workload, freeze)
            self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
