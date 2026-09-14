"""Small offline tests: unchanged request implementation, strict suffix and cleanup.

The real frozen adapter/backend/client parse fake HTTP only. No Ollama call,
real ONNX session, telemetry subprocess, or source-freeze mutation is made.
"""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import independent_retrieval_fragment_worker as worker
from independent_retrieval_adapter import materialize_snapshot
from tests.test_complete_system_runner import FakeEmbedder, seed
from tests.test_lightweight_integration import RecordingTransport
from tests.test_post_memory_comparison import FakeSampler, snapshot


class FragmentWorkerTests(unittest.TestCase):
    def fixture(self,path,model="qwen3:1.7b",policy="SELECTIVE"):
        freeze=path/"freeze";freeze.mkdir();prepared=freeze/"prepared_snapshot";prepared.mkdir()
        memory_seed=seed();memory_seed["retention_days"]=30
        materialize_snapshot(prepared/"memory.sqlite3",memory_seed,FakeEmbedder())
        cases=[{"id":f"case_{index:02d}","prompt":"Arrange an exhibition.",
                "profile_id":memory_seed["profile_id"],"consent_authorized":True} for index in range(48)]
        slot={"slot":4,"model":model,"policy":policy,"repetition":1,
              "request_ids":[case["id"] for case in cases]}
        (freeze/"freeze.json").write_text("{}")
        baseline=path/"baseline.json";baseline.write_text(json.dumps(snapshot()))
        continuation=path/"continuation";continuation.mkdir()
        ledger=path/"ledger";ledger.mkdir()
        for directory,name in ((continuation,"continuation.json"),(ledger,"ledger.json")):
            (directory/name).write_text("{}");(directory/"seal.json").write_text("{}")
        args=SimpleNamespace(freeze=freeze,continuation=continuation,ledger=ledger,slot=4,
                             offset=46,output=path/"fragment",baseline=baseline)
        frozen={"schedule":[{"slot":1},{"slot":2},{"slot":3},slot]}
        runtime={"memory_seed":memory_seed,"execution_cases":cases}
        proof={"slot":4,"offset":46,"request_ids":slot["request_ids"][46:],"baseline":str(baseline),
               "authorized_worker_directory":str(args.output)}
        return args,({},proof,frozen,runtime,slot,slot["request_ids"][46:])

    def test_verified_inputs_requires_exact_nonempty_suffix_and_original_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            args,values=self.fixture(Path(temporary))
            with patch.object(worker,"verify_continuation",return_value=values[0]), \
                 patch.object(worker,"verify_ledger",return_value=values[1]) as ledger_check, \
                 patch.object(worker.runner,"verify_frozen",return_value=values[2:4]):
                self.assertEqual(worker.verified_inputs(args),values)
                ledger_check.assert_called_once_with(args.freeze,args.continuation,args.ledger,4,46)
                for bad in (dict(values[1],offset=45),dict(values[1],request_ids=values[-1][1:]),
                            dict(values[1],baseline=str(Path(temporary)/"other.json")),
                            dict(values[1],authorized_worker_directory=str(Path(temporary)/"replay"))):
                    ledger_check.return_value=bad
                    with self.assertRaises(ValueError):worker.verified_inputs(args)
                ledger_check.return_value=values[1];args.offset=48
                with self.assertRaises(ValueError):worker.verified_inputs(args)

    def execute(self,args,values,transport,*,final_integrity_error=False,check=None):
        actual_client=worker.runner.DurableClient
        def client(*args,**kwargs):return actual_client(*args,opener=transport,**kwargs)
        def state():
            value=snapshot();value["resident_models"]=sorted(transport.resident);return value
        inputs=[values,ValueError("offline modified supplemental source")] if final_integrity_error else [values,values]
        with ExitStack() as stack:
            stack.enter_context(patch.object(worker,"verified_inputs",side_effect=inputs))
            stack.enter_context(patch.object(worker.runner,"require_exclusive"))
            stack.enter_context(patch.object(worker.runner,"DurableClient",side_effect=client))
            stack.enter_context(patch.object(worker.runner,"BgeOnnxEmbedder",side_effect=lambda *a:FakeEmbedder()))
            stack.enter_context(patch.object(worker.runner,"GuardedSampler",FakeSampler))
            stack.enter_context(patch.object(worker.runner.ComparisonBackend,"check",side_effect=check,return_value={}))
            stack.enter_context(patch.object(worker.runner.pair,"capture_safety_snapshot",side_effect=state))
            stack.enter_context(patch.object(worker.runner.pair,"_resident_models",side_effect=lambda:sorted(transport.resident)))
            stack.enter_context(redirect_stdout(io.StringIO()))
            result=worker._session(args)
        worker.runner.verify_seal(args.output)
        def read(name):return json.loads((args.output/name).read_text())
        rows=[json.loads(line) for line in (args.output/"observations.jsonl").read_text().splitlines()]
        return result,read("manifest.json"),read("summary.json"),rows

    def test_real_runner_only_executes_suffix_and_retains_sole_model(self):
        for model in ("qwen3:0.6b","qwen3:1.7b"):
            with self.subTest(model=model),tempfile.TemporaryDirectory() as temporary:
                args,values=self.fixture(Path(temporary),model)
                transport=RecordingTransport()
                result,manifest,summary,rows=self.execute(args,values,transport)
                self.assertEqual(result,0);self.assertEqual(summary["status"],"complete")
                self.assertEqual(summary["planned"],2);self.assertEqual(summary["original_planned"],48)
                self.assertEqual(summary["attempted"],2);self.assertEqual(summary["fragment_offset"],46)
                self.assertEqual(manifest["slot"],values[4]);self.assertEqual(manifest["fragment"]["request_ids"],values[-1])
                self.assertEqual([row["case"]["id"] for row in rows],["case_46","case_47"])
                self.assertEqual([row["index"] for row in rows],[1,2])
                self.assertEqual(rows[0]["api_ps_before"],[])
                self.assertEqual(rows[0]["api_ps_after"],[model]);self.assertEqual(rows[1]["api_ps_before"],[model])
                self.assertEqual({call["body"]["model"] for call in transport.requests},{model})
                self.assertEqual(len(transport.classifiers),2);self.assertEqual(len(transport.generations),2)
                self.assertEqual(len([call for call in transport.requests if call["endpoint"]=="generate"]),1)
                for call in transport.chats:
                    self.assertEqual(call["body"]["options"],{"num_ctx":2048,"num_predict":192,"temperature":0.0,"seed":42})
                    self.assertIs(call["body"]["think"],False)
                for call in transport.generations:
                    self.assertEqual([m["role"] for m in call["body"]["messages"]],["system","user"])
                self.assertEqual(transport.classifiers[0]["body"]["messages"],transport.classifiers[1]["body"]["messages"])
                self.assertEqual(transport.resident,set())
                snapshot_check=json.loads((args.output/"snapshot_verification.json").read_text())
                self.assertTrue(snapshot_check["unchanged"])
                self.assertEqual(snapshot_check["before"],worker.runner.file_hash(args.freeze/"prepared_snapshot/memory.sqlite3"))

    def test_interrupted_request_is_durable_and_next_suffix_case_is_not_attempted(self):
        with tempfile.TemporaryDirectory() as temporary:
            args,values=self.fixture(Path(temporary));transport=RecordingTransport()
            crossed=[];transport.after_generation=lambda:crossed.append(True)
            def check():
                if crossed:raise worker.runner.pair.SafetyGateError("offline runtime floor")
                return {}
            result,_,summary,rows=self.execute(args,values,transport,check=check)
            self.assertEqual(result,1);self.assertEqual(summary["status"],"interrupted")
            self.assertEqual(summary["attempted"],1);self.assertEqual(rows[0]["status"],"interrupted")
            self.assertEqual(rows[0]["case"]["id"],"case_46")
            self.assertEqual(summary["failure"]["type"],"SafetyGateError")
            self.assertEqual(summary["cleanup_errors"],[]);self.assertEqual(transport.resident,set())
            events=[json.loads(line) for line in (args.output/"events.jsonl").read_text().splitlines()]
            self.assertEqual([item["request_id"] for item in events if item["event"]=="request_start"],["case_46"])
            self.assertTrue((args.output/"cleanup_timing.json").exists())

    def test_final_integrity_failure_preserves_successful_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            args,values=self.fixture(Path(temporary));transport=RecordingTransport()
            result,_,summary,rows=self.execute(args,values,transport,final_integrity_error=True)
            self.assertEqual(result,1);self.assertEqual(summary["status"],"verification_failed")
            self.assertEqual(len(rows),2);self.assertTrue(all(row["status"]=="ok" for row in rows))
            self.assertIn("supplemental source",summary["cleanup_errors"][0]);self.assertEqual(transport.resident,set())


if __name__=="__main__":unittest.main()
