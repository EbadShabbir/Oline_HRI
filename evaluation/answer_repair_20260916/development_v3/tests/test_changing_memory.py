"""Offline harness checks: real SQLite/retrieval/conversation, synthetic inference.

These are harness regressions, never completed live experimental checkpoints.
The subprocess entry point deliberately does not load models or use HTTP.
"""

from contextlib import ExitStack, nullcontext, redirect_stdout
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import run_changing_memory as runner
from oline_hri.cli import _run_memory
from oline_hri.config import load_config
from oline_hri.ollama import ChatMessage
from test_conversation_routed import FakeBackend, chat_result
from test_memory import FakeEmbedder


DRAFT = ROOT / "evaluation/changing_memory_20260914/authored_v2"
BASE = "2026-10-01T12:00:00+00:00"
QUESTION = "What is my preferred tea?"
ORIGINAL = "Your preferred tea is rooibos tea."
REPLACEMENT = "Your preferred tea is jasmine tea."


class ListWriter:
    def __init__(self):
        self.rows = []

    def write(self, row):
        # Like a durable JSON writer, detach the event from mutable live state.
        self.rows.append(json.loads(json.dumps(row)))


class OfflineBackend:
    """Schema-driven test responses; never oracle/ledger-driven responses."""

    def __init__(self):
        self.calls, self.transport_error = [], None
        self.generator = FakeBackend()
        self.failure = None

    def check(self):
        pass

    def chat(self, model, messages, *, response_format=None, **kwargs):
        fields = response_format["properties"]
        if "memory_required" in fields:
            encoded = json.loads(messages[-1].content.split("\n", 1)[1])
            current = encoded["current_user_text"]
            statement = not current.rstrip().endswith("?")
            result = chat_result(raw=json.dumps({"form": "statement" if statement else "question",
                                                "memory_required": not statement}), model=model)
            purpose = "memory_selector"
        elif "model_size" in fields:
            result = chat_result(raw='{"model_size":"small"}', model=model)
            purpose = "compute_selector"
        else:
            purpose = "generation"
            if self.failure is not None:
                error, self.failure = self.failure, None
                self.calls.append({"purpose": purpose, "messages": [m.to_dict() for m in messages],
                                   "requested_model": model, "status": "error", "error": type(error).__name__})
                raise error
            if "enum" in fields["speech"]:
                ids = tuple(fields["memory_used"]["items"].get("enum", ()))
                result = chat_result(fields["speech"]["enum"][0], memory_used=ids, model=model)
            else:
                result = self.generator.chat(model, messages, response_format=response_format)
        self.calls.append({"purpose": purpose, "messages": [m.to_dict() for m in messages],
                           "requested_model": model, "actual_model": result.model,
                           "generation": asdict(result), "status": "ok"})
        return result


def authored_branch(kind="correction"):
    runtime = json.loads((DRAFT / "runtime.json").read_text())
    return next(b for b in runtime["branches"] if b["scenario_id"] == "cm01" and b["branch"] == kind)


def offline_worker(parameters):
    if parameters.get("mode") == "production_worker":
        return offline_production_worker(parameters)
    answers, events, backend = ListWriter(), ListWriter(), OfflineBackend()
    episode = runner.Episode(parameters["branch"], Path(parameters["database"]), backend,
                             FakeEmbedder(), answers, events, restored=parameters.get("restored"))
    opened_time = episode.clock().isoformat()
    with redirect_stdout(io.StringIO()):
        for op in parameters["operations"]:
            episode.operation(op)
    return {"pid": os.getpid(), "opened_time": opened_time, "state": episode.state(),
            "answers": answers.rows, "events": events.rows,
            "snapshot": runner.database_snapshot(parameters["database"])}


def offline_production_worker(parameters):
    """Run the actual worker control flow, replacing only hardware/model I/O."""
    backend = OfflineBackend()
    if parameters.get("interrupt"):
        backend.failure = KeyboardInterrupt("offline interrupted checkpoint")

    class Sampler:
        def __init__(self, monitor):
            self.monitor = monitor

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def summary(self):
            return {"scope": "offline fake sampler"}

    snapshot = {"boot_id": "offline", "power_mode": "offline", "thermal_trip_events": 0,
                "memory": {"swap_total_kib": 0}, "resident_models": []}
    with ExitStack() as stack:
        lease_paths = (Path("/tmp/clara-jetson-inference.lock"),
                       ROOT / "evaluation/independent_retrieval_inference.lock",
                       ROOT / "evaluation/matched_evidence_inference.lock")
        leases = [stack.enter_context(path.open("a")) for path in lease_paths]
        patches = (
            patch.object(runner, "verify_frozen", return_value={}),
            patch.object(runner, "stage2_limits", side_effect=nullcontext),
            patch.object(runner, "require_ready"),
            patch.object(runner, "require_baseline"),
            patch.object(runner.pair, "capture_safety_snapshot",
                         side_effect=[snapshot, RuntimeError("offline final capture failure")]
                         if parameters.get("fail_final_capture") else None, return_value=snapshot),
            patch.object(runner, "DurableClient", return_value=object()),
            patch.object(runner, "ComparisonBackend", return_value=backend),
            patch.object(runner, "GuardedSampler", Sampler),
            patch.object(runner, "initial_sample"),
            patch.object(runner, "BgeOnnxEmbedder", return_value=FakeEmbedder()),
            patch.object(runner, "cleanup_owned", return_value=[]),
        )
        for replacement in patches:
            stack.enter_context(replacement)
        args = SimpleNamespace(freeze=Path(parameters["freeze"]), output=Path(parameters["output"]),
                               database=Path(parameters["database"]), branch=parameters["branch_id"],
                               segment="initial", start_offset=parameters.get("start_offset", 0),
                               state=Path(parameters["state"]) if parameters.get("state") else None,
                               lease_fds=",".join(str(lease.fileno()) for lease in leases))
        with redirect_stdout(io.StringIO()):
            returncode = runner.worker(args)
    return {"pid": os.getpid(), "returncode": returncode}


class ChangingMemoryHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "fictional.sqlite3"
        self.answers, self.events = ListWriter(), ListWriter()
        self.backend, self.embedder = OfflineBackend(), FakeEmbedder()

    def episode(self, branch=None, restored=None):
        return runner.Episode(branch or authored_branch(), self.database, self.backend,
                              self.embedder, self.answers, self.events, restored=restored)

    def run_op(self, episode, operation, *, time=BASE, **kwargs):
        with redirect_stdout(io.StringIO()):
            return episode.operation({"op": operation, "time": time, **kwargs})

    def remember(self, episode):
        self.run_op(episode, "remember", text=ORIGINAL, record_key="subject", kind="preference")
        return episode.store.list_memories()[0]

    def last_operation(self, name):
        return next(row for row in reversed(self.events.rows)
                    if row.get("event") == "operation" and row["op"]["op"] == name)

    def external(self, branch, operations, restored=None):
        params = {"branch": branch, "database": str(self.database), "operations": operations,
                  "restored": restored}
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--offline-worker"],
                               input=json.dumps(params), capture_output=True, text=True,
                               env=env, timeout=40, check=True)
        result = json.loads(child.stdout)
        self.assertNotEqual(result["pid"], os.getpid())
        return result

    def test_actual_authored_schema_runs_all_initial_operations_without_oracle_inputs(self):
        runtime = json.loads((DRAFT / "runtime.json").read_text())
        ledger = json.loads((DRAFT / "expected_ledger.json").read_text())
        planned = {c["checkpoint_id"] for c in ledger["checkpoints"]}
        executed = set()
        self.assertEqual(len(runtime["branches"]), 36)
        self.assertEqual(len({b["scenario_id"] for b in runtime["branches"]}), 12)
        for branch in runtime["branches"]:
            with self.subTest(branch=branch["branch_id"]):
                self.database = Path(self.temporary.name) / (branch["branch_id"] + ".sqlite3")
                self.answers, self.events = ListWriter(), ListWriter()
                self.backend, self.embedder = OfflineBackend(), FakeEmbedder()
                episode = self.episode(branch)
                for operation in branch["operations"]:
                    if operation["op"] == "restart":
                        break
                    with redirect_stdout(io.StringIO()):
                        episode.operation(operation)
                mutation_rows = [r for r in self.events.rows if r.get("event") == "operation"]
                self.assertTrue(mutation_rows)
                self.assertTrue(all(r["status"] == "ok" for r in mutation_rows))
                for row in self.answers.rows:
                    if row["checkpoint_id"]:
                        executed.add(row["checkpoint_id"])
                        self.assertIn(row["checkpoint_id"], planned)
                    # A real validator may reject synthetic answers. Preserve
                    # that outcome while requiring a completed logged attempt.
                    self.assertIn(row["status"], ("delivered", "withheld"))
                    if row["status"] == "withheld":
                        self.assertEqual(row["error"], "ResponseValidationError", row.get("message"))
                        self.assertIsNone(row["delivered_answer"])
                    self.assertTrue(row["calls"])
                    self.assertTrue(row["raw_model_answers"])
                    encoded = json.dumps(row["calls"])
                    for secret_key in ("expected_value", "forbidden_values", "authorized_state", "required_behavior"):
                        self.assertNotIn(secret_key, encoded)
        expected_initial = {c["checkpoint_id"] for c in ledger["checkpoints"] if not c["after_restart"]}
        self.assertEqual(executed, expected_initial)

    def test_cli_acknowledgments_mutate_same_live_store_and_keep_original_history(self):
        episode = self.episode()
        history_marker = "Please acknowledge this personal statement: My preferred tea is rooibos tea."
        episode.conversation._messages.append(ChatMessage("user", history_marker))
        with patch.object(runner, "_run_memory", wraps=_run_memory) as dispatch:
            original = self.remember(episode)
            self.assertIn("remembered " + original.id, self.last_operation("remember")["acknowledgement"])
            self.run_op(episode, "cache_probe", query=QUESTION, target_key="subject")
            self.assertTrue(self.last_operation("cache_probe")["snapshot_current"])
            self.run_op(episode, "correct", time="2026-10-01T12:01:00+00:00", text=REPLACEMENT,
                        target_key="subject")
            replacement = episode.store.list_memories()[0]
            self.assertEqual(replacement.canonical_text, REPLACEMENT)
            self.assertEqual(replacement.supersedes_id, original.id)
            self.assertEqual(replacement.retention_until, original.retention_until)
            self.assertIn("corrected " + original.id, self.last_operation("correct")["acknowledgement"])
            self.run_op(episode, "snapshot_probe", time="2026-10-01T12:01:00+00:00")
            self.assertFalse(self.last_operation("snapshot_probe")["snapshot_current"])
            self.assertEqual([m.memory.id for m in episode.retriever.retrieve(QUESTION)], [replacement.id])
            self.run_op(episode, "forget", time="2026-10-01T12:02:00+00:00", target_key="subject")
            self.assertEqual(dispatch.call_count, 3)
        self.assertIn("removed 2 revision(s)", self.last_operation("forget")["acknowledgement"])
        self.assertEqual(episode.store.list_memories(include_inactive=True), ())
        self.assertEqual(episode.retriever.retrieve(QUESTION), ())
        self.assertEqual(episode.conversation.messages[-1].content, history_marker)
        self.assertGreaterEqual(len(self.embedder.passage_calls), 2)
        embeddings = [r for r in self.events.rows if r.get("event") == "embedding"]
        self.assertTrue(all(r["vector_sha256"] and r["logical_time"] for r in embeddings))

    def test_configured_expiry_uses_shared_clock_at_exact_boundary_without_db_edits(self):
        episode = self.episode(authored_branch("expiry"))
        original = self.remember(episode)
        boundary = datetime.fromisoformat(original.retention_until.replace("Z", "+00:00"))
        self.assertEqual(boundary - datetime.fromisoformat(BASE), timedelta(days=load_config().memory.retention_days))
        episode.clock.set((boundary - timedelta(microseconds=1)).isoformat())
        retained = episode.retriever.retrieve(QUESTION)
        self.assertEqual([m.memory.id for m in retained], [original.id])
        self.assertTrue(episode.retriever.is_current(retained))
        before = runner.database_snapshot(self.database)
        episode.clock.set(boundary.isoformat())
        self.assertEqual(runner.database_snapshot(self.database), before)
        self.assertFalse(episode.retriever.is_current(retained))
        self.assertEqual(episode.retriever.retrieve(QUESTION), ())
        episode.clock.set((boundary + timedelta(microseconds=1)).isoformat())
        self.assertEqual(episode.retriever.retrieve(QUESTION), ())
        self.assertFalse(episode.retriever.is_current(retained))
        for check in episode.retriever.checks[1:]:
            self.assertGreaterEqual(datetime.fromisoformat(check["logical_time"]), boundary)

    def test_fresh_queries_do_not_modify_retained_history_and_log_supplied_evidence(self):
        episode = self.episode()
        disclosure = next(op for op in episode.branch["operations"] if op["op"] == "disclose")
        with redirect_stdout(io.StringIO()):
            episode.operation(disclosure)
        original = self.remember(episode)
        row = self.run_op(episode, "ask", question=QUESTION, checkpoint_id="retained", history="retained")
        self.assertEqual(row["status"], "delivered", row.get("message"))
        self.assertIn("rooibos", row["delivered_answer"])
        saved = episode.state()["history"]
        fresh = self.run_op(episode, "ask", question=QUESTION, checkpoint_id="fresh", history="fresh")
        self.assertEqual(episode.state()["history"], saved)
        self.assertLess(len(fresh["history_before"]), len(saved))
        self.assertEqual([m["id"] for m in fresh["supplied_records"]], [original.id])
        self.assertTrue(all(c["current"] for c in fresh["snapshot_checks"]))
        self.assertEqual(fresh["validation_decision"], "accepted")
        self.assertEqual(fresh["process"]["pid"], os.getpid())
        self.assertEqual({c["purpose"] for c in fresh["calls"]},
                         {"memory_selector", "compute_selector", "generation"})

    def test_stale_snapshot_replay_is_withheld_before_generation_and_preserved(self):
        episode = self.episode()
        self.remember(episode)
        old = episode.retriever.retrieve(QUESTION)
        self.run_op(episode, "forget", target_key="subject")
        before = episode.state()["history"]
        episode.retriever.inject_snapshot = old
        row = self.run_op(episode, "ask", question=QUESTION, checkpoint_id="stale")
        self.assertEqual(row["status"], "withheld")
        self.assertIsNone(row["delivered_answer"])
        self.assertIn("no longer current", row["message"])
        self.assertEqual(row["raw_model_answers"], [])
        self.assertFalse(row["snapshot_checks"][-1]["current"])
        self.assertTrue(row["retrieval_calls"][0]["diagnostic_snapshot_replay"])
        self.assertEqual(episode.state()["history"], before)
        self.assertEqual(self.answers.rows[-1], row)

    def test_generation_interruption_is_logged_before_propagation(self):
        episode = self.episode()
        self.remember(episode)
        self.backend.failure = KeyboardInterrupt("offline injected interruption")
        before = episode.state()["history"]
        with self.assertRaises(KeyboardInterrupt):
            self.run_op(episode, "ask", question=QUESTION, checkpoint_id="interrupt")
        row = self.answers.rows[-1]
        self.assertEqual(row["status"], "interrupted")
        self.assertEqual(row["error"], "KeyboardInterrupt")
        self.assertIsNone(row["delivered_answer"])
        self.assertTrue(row["database_after"]["memory_item"])
        self.assertEqual(episode.state()["history"], before)

    def test_actual_process_restarts_preserve_mutations_history_and_nonempty_snapshots(self):
        for kind in ("correction", "deletion", "expiry"):
            with self.subTest(branch=kind):
                self.database = Path(self.temporary.name) / (kind + ".sqlite3")
                branch = authored_branch(kind)
                restart = next(i for i, op in enumerate(branch["operations"]) if op["op"] == "restart")
                first = self.external(branch, branch["operations"][:restart])
                second = self.external(branch, branch["operations"][restart + 1:], first["state"])
                self.assertNotEqual(first["pid"], second["pid"])
                restored = next(r for r in second["events"] if r.get("event") == "history_restored_after_process_restart")
                self.assertEqual(restored["exact_history"], first["state"]["history"])
                self.assertGreaterEqual(datetime.fromisoformat(second["opened_time"]),
                                        datetime.fromisoformat(branch["operations"][restart - 1]["time"]))
                snapshot = next(r for r in second["events"]
                                if r.get("event") == "operation" and r["op"]["op"] == "snapshot_probe")
                self.assertTrue(snapshot["retained_snapshot"], "empty snapshot makes restart exclusion vacuous")
                self.assertFalse(snapshot["snapshot_current"])
                current = [r for r in second["answers"] if "historical" not in (r["checkpoint_id"] or "")]
                self.assertTrue(current)
                for row in current:
                    self.assertEqual(row["status"], "delivered", row.get("message"))
                    self.assertNotIn("rooibos", row["delivered_answer"])
                    if kind == "correction":
                        self.assertIn("jasmine", row["delivered_answer"])
                    else:
                        self.assertEqual(row["supplied_records"], [])

    def test_same_process_reconstruction_and_backward_clock_are_rejected(self):
        episode = self.episode()
        self.remember(episode)
        with self.assertRaisesRegex(ValueError, "not a process restart"):
            self.episode(restored=episode.state())
        episode.clock.set("2026-10-02T12:00:00+00:00")
        for invalid in (BASE, "2026-10-03T12:00:00"):
            with self.assertRaises((ValueError, TypeError)):
                episode.clock.set(invalid)

    def test_worker_continuation_preserves_interrupted_checkpoint_and_executes_only_suffix(self):
        branch = authored_branch()
        branch["operations"] = [
            {"op": "remember", "time": BASE, "text": ORIGINAL, "record_key": "subject", "kind": "preference"},
            {"op": "ask", "time": BASE, "question": QUESTION, "checkpoint_id": "interrupted"},
            {"op": "correct", "time": "2026-10-01T12:01:00+00:00", "text": REPLACEMENT, "target_key": "subject"},
            {"op": "ask", "time": "2026-10-01T12:01:01+00:00", "question": QUESTION, "checkpoint_id": "continued"},
            {"op": "restart", "time": "2026-10-01T12:02:00+00:00"},
            # The harness records the authored disclosure text in diagnostics.
            # It is after the segment and is not executed by this worker test.
            {"op": "disclose", "time": "2026-10-01T12:02:01+00:00", "text": "Offline marker"},
        ]
        freeze = Path(self.temporary.name) / "offline-freeze"
        freeze.mkdir()
        (freeze / "runtime.json").write_text(json.dumps({"branches": [branch]}))
        parameters = {"mode": "production_worker", "database": str(self.database),
                      "freeze": str(freeze), "branch_id": branch["branch_id"]}

        def launch(**extra):
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--offline-worker"],
                                  input=json.dumps({**parameters, **extra}), text=True, capture_output=True,
                                  timeout=40, check=True, env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))
            return json.loads(proc.stdout)

        first_dir = Path(self.temporary.name) / "interrupted"
        first = launch(output=str(first_dir), interrupt=True)
        first_finish = json.loads((first_dir / "finish.json").read_text())
        self.assertEqual(first["returncode"], 1)
        self.assertEqual(first_finish["status"], "interrupted")
        self.assertEqual(first_finish["next_offset"], 2)
        self.assertEqual(first_finish["operation_count"], 4)
        first_answers = [json.loads(line) for line in (first_dir / "answers.jsonl").read_text().splitlines()]
        self.assertEqual([r["checkpoint_id"] for r in first_answers], ["interrupted"])
        self.assertEqual(first_answers[0]["status"], "interrupted")
        state = first_dir / "state_after_001.json"
        self.assertTrue(state.is_file())
        first_hashes = {p.name: runner.digest(p) for p in first_dir.iterdir() if p.is_file()}
        next_dir = Path(self.temporary.name) / "continuation"
        second = launch(output=str(next_dir), state=str(state), start_offset=2)
        self.assertEqual(second["returncode"], 0)
        self.assertNotEqual(first["pid"], second["pid"])
        second_finish = json.loads((next_dir / "finish.json").read_text())
        self.assertEqual(second_finish["next_offset"], 4)
        answers = [json.loads(line) for line in (next_dir / "answers.jsonl").read_text().splitlines()]
        self.assertEqual([r["checkpoint_id"] for r in answers], ["continued"])
        self.assertEqual(answers[0]["status"], "delivered")
        self.assertIn("jasmine", answers[0]["delivered_answer"])
        events = [json.loads(line) for line in (next_dir / "events.jsonl").read_text().splitlines()]
        self.assertEqual([r["op"]["op"] for r in events if r.get("event") == "operation"], ["correct"])
        self.assertEqual(first_hashes, {p.name: runner.digest(p) for p in first_dir.iterdir() if p.is_file()})

    def test_source_and_config_drift_rejected_before_model_inventory_access(self):
        frozen = {"source_sha256": {"source.py": "frozen"}, "config": load_config().to_dict(),
                  "models": ["offline"], "ollama_version": {"version": "offline"}}
        directory = Path(self.temporary.name) / "freeze"
        directory.mkdir()
        (directory / "freeze.json").write_text(json.dumps(frozen))
        for drift in ("source", "config"):
            with self.subTest(drift=drift):
                value = deepcopy(frozen)
                if drift == "config":
                    value["config"]["memory"]["retention_days"] += 1
                    (directory / "freeze.json").write_text(json.dumps(value))
                with patch.object(runner, "verify_seal"), \
                     patch.object(runner, "sources", return_value={"source.py": "changed"} if drift == "source" else frozen["source_sha256"]), \
                     patch.object(runner, "model_inventory", side_effect=AssertionError("must reject before model HTTP")):
                    with self.assertRaisesRegex(ValueError, "source/configuration differs"):
                        runner.verify_frozen(directory)

    def test_supervisor_passes_persisted_state_and_only_unstarted_suffix_to_continuation(self):
        frozen = Path(self.temporary.name) / "supervisor-freeze"
        frozen.mkdir()
        branch = authored_branch()
        (frozen / "runtime.json").write_text(json.dumps({"branches": [branch]}))
        launched = []

        class Process:
            def __init__(inner, command, **kwargs):
                options = dict(zip(command[3::2], command[4::2]))
                launched.append((options, kwargs["pass_fds"]))
                directory = Path(options["--output"])
                directory.mkdir()
                segment, offset = options["--segment"], int(options["--start-offset"])
                interrupted = segment == "initial" and offset == 0
                count, next_offset = (4, 2) if interrupted else (4, 4) if segment == "initial" else (2, 2)
                state = {"offline_state_marker": directory.name}
                runner.write(directory / f"state_after_{next_offset - 1:03}.json", state)
                if not interrupted:
                    runner.write(directory / "state.json", state)
                runner.write(directory / "finish.json", {"next_offset": next_offset, "operation_count": count,
                              "status": "interrupted" if interrupted else "complete", "cleanup_errors": []})
                inner.pid, inner.returncode = 12300 + len(launched), int(interrupted)

            def wait(inner):
                return inner.returncode

        output = Path(self.temporary.name) / "supervisor-run"
        with patch.object(runner, "verify_frozen", return_value={}), \
             patch.object(runner, "inference_lock", return_value=nullcontext((71, 72, 73))), \
             patch.object(runner, "stage2_limits", side_effect=nullcontext), \
             patch.object(runner.pair, "capture_safety_snapshot", return_value={}), \
             patch.object(runner, "require_ready"), patch.object(runner, "require_baseline"), \
             patch.object(runner.subprocess, "Popen", Process), redirect_stdout(io.StringIO()):
            code = runner.collect(SimpleNamespace(freeze=frozen, output=output))
        self.assertEqual(code, 0)
        self.assertEqual(len(launched), 3)
        self.assertEqual([o["--start-offset"] for o, _ in launched], ["0", "2", "0"])
        self.assertEqual([o["--segment"] for o, _ in launched], ["initial", "initial", "restart"])
        self.assertTrue(all(fds == (71, 72, 73) for _, fds in launched))
        self.assertNotIn("--state", launched[0][0])
        self.assertEqual(Path(launched[1][0]["--state"]),
                         output / branch["branch_id"] / "initial/state_after_001.json")
        self.assertEqual(Path(launched[2][0]["--state"]),
                         output / branch["branch_id"] / "initial_continuation_02/state.json")
        finish = json.loads((output / "finish.json").read_text())
        self.assertEqual([r["returncode"] for r in finish["segments"]], [1, 0, 0])

    def test_worker_rejects_missing_partial_or_wrong_file_leases_before_runtime_access(self):
        with tempfile.TemporaryFile() as wrong, \
             patch.object(runner, "verify_frozen", side_effect=AssertionError("must reject before runtime access")):
            for leases, error in (("", "inherited exclusive"), (str(wrong.fileno()), "all three"),
                                  (",".join([str(wrong.fileno())] * 3), "does not match")):
                with self.subTest(leases=leases), self.assertRaisesRegex(ValueError, error):
                    runner.worker(SimpleNamespace(lease_fds=leases))

    def test_worker_final_capture_failure_preserves_answers_but_returns_failure(self):
        branch = authored_branch()
        frozen = Path(self.temporary.name) / "capture-freeze"
        frozen.mkdir()
        (frozen / "runtime.json").write_text(json.dumps({"branches": [branch]}))
        output = Path(self.temporary.name) / "capture-run"
        result = offline_production_worker({"database": str(self.database), "freeze": str(frozen),
                    "branch_id": branch["branch_id"], "output": str(output), "fail_final_capture": True})
        self.assertEqual(result["returncode"], 1)
        finish = json.loads((output / "finish.json").read_text())
        self.assertEqual(finish["status"], "complete")
        self.assertEqual(finish["next_offset"], finish["operation_count"])
        self.assertEqual(finish["cleanup_errors"], ["final resource/invariant capture failed: RuntimeError"])
        self.assertEqual(finish["snapshot"], {"error": "RuntimeError", "message": "offline final capture failure"})
        self.assertTrue((output / "state.json").is_file())
        self.assertTrue((output / "answers.jsonl").read_text())
        runner.verify_seal(output)

    def test_supervisor_interrupt_reaps_worker_and_unloads_before_sealing(self):
        frozen = Path(self.temporary.name) / "stop-freeze"
        frozen.mkdir()
        branch = authored_branch()
        (frozen / "runtime.json").write_text(json.dumps({"branches": [branch]}))
        actual_seal = runner.seal
        for escalation in (0, 1, 2):
            with self.subTest(escalation=escalation):
                events, reaped = [], []
                output = Path(self.temporary.name) / f"stop-{escalation}"

                class Process:
                    def __init__(inner, command, **kwargs):
                        inner.pid, inner.returncode, inner.stage = 32123, None, 0
                        options = dict(zip(command[3::2], command[4::2]))
                        directory = Path(options["--output"])
                        directory.mkdir()
                        (directory / "answers.jsonl").write_text(json.dumps({"checkpoint_id": "completed-before-stop"}) + "\n")

                    def wait(inner, timeout=None):
                        events.append(("wait", timeout))
                        if timeout is None:
                            raise KeyboardInterrupt("offline supervisor interrupt")
                        if inner.stage < escalation:
                            raise subprocess.TimeoutExpired("offline worker", timeout)
                        inner.returncode = -2 if inner.stage == 0 else -15 if inner.stage == 1 else -9
                        reaped.append(True)
                        return inner.returncode

                    def send_signal(inner, signal):
                        events.append(("signal", signal))

                    def terminate(inner):
                        inner.stage = 1
                        events.append(("terminate", None))

                    def kill(inner):
                        inner.stage = 2
                        events.append(("kill", None))

                def unload(models):
                    self.assertTrue(reaped, "model cleanup must follow worker reaping")
                    self.assertEqual(models, runner.MODELS)
                    events.append(("unload", None))
                    return []

                def seal(path):
                    self.assertTrue(reaped, "never seal output while worker can still append")
                    self.assertEqual(events[-1], ("unload", None))
                    self.assertTrue((output / branch["branch_id"] / "initial_supervisor_stop.json").is_file())
                    events.append(("seal", None))
                    return actual_seal(path)

                with patch.object(runner, "verify_frozen", return_value={}), \
                     patch.object(runner, "inference_lock", return_value=nullcontext((71, 72, 73))), \
                     patch.object(runner, "stage2_limits", side_effect=nullcontext), \
                     patch.object(runner.pair, "capture_safety_snapshot", return_value={}), \
                     patch.object(runner, "require_ready"), patch.object(runner, "require_baseline"), \
                     patch.object(runner.subprocess, "Popen", Process), \
                     patch.object(runner.pair, "_force_unload", side_effect=unload), \
                     patch.object(runner, "seal", side_effect=seal), redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(KeyboardInterrupt, "offline supervisor interrupt"):
                        runner.collect(SimpleNamespace(freeze=frozen, output=output))
                expected = [("wait", None), ("signal", runner.signal.SIGINT), ("wait", 30)]
                if escalation >= 1:
                    expected += [("terminate", None), ("wait", 10)]
                if escalation == 2:
                    expected += [("kill", None), ("wait", 10)]
                self.assertEqual(events, expected + [("unload", None), ("seal", None)])
                stop = json.loads((output / branch["branch_id"] / "initial_supervisor_stop.json").read_text())
                self.assertEqual(stop["returncode"], (-2, -15, -9)[escalation])
                interruption = json.loads((output / "orchestration_interruption.json").read_text())
                self.assertEqual(interruption["recorded_checkpoint_ids"], ["completed-before-stop"])
                runner.verify_seal(output)


if __name__ == "__main__":
    if sys.argv[1:] == ["--offline-worker"]:
        print(json.dumps(offline_worker(json.loads(sys.stdin.read()))))
    else:
        unittest.main()
