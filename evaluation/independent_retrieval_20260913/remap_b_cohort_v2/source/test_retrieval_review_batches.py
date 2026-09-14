"""Small stdlib-only packet parity and blinded exact-content reuse checks."""
import ast
from collections import defaultdict
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import random
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import batch_independent_retrieval_reviews as batches
review=batches.review


class ReviewBatchTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.count=0
        self.instructions=self.root/"instructions.md";self.instructions.write_text(batches.instructions_from_source())

    def packet(self,number=1,**extra):
        return {"review_id":"review_"+f"{number:032x}","prompt":"What is my fictional album called?",
            "answer":"Your album is Leafglass.","delivery_status":"delivered","answerability":"known_authorized",
            "rubric":{"required_semantic_claims":["The album is Leafglass."]},
            "reference_facts_without_ids":["Your fictional album is Leafglass."],**extra}

    def judgment(self,packet,label="complete",**extra):
        return {"review_id":packet["review_id"],"label":label,"rationale":"The requested answer is present.",
                **{flag:False for flag in review.FLAGS},**extra}

    def call(self,function,args):
        with redirect_stdout(io.StringIO()):function(args,[function.__name__,"--output",str(args.output)])
        review.verify_seal(args.output)
        return args.output

    def frozen_batch(self,packets,judgments=None,reviewer="Assistant A",aliases=()):
        self.count+=1;inputs=self.root/f"input_{self.count}";inputs.mkdir()
        packet=inputs/"packet.jsonl";sheet=inputs/"sheet.jsonl"
        review.write_lines(packet,packets);review.write_lines(sheet,judgments or [self.judgment(item) for item in packets])
        return self.call(batches.freeze_review,SimpleNamespace(packet=packet,instructions=self.instructions,sheet=sheet,
            reviewer=reviewer,alias=list(aliases),output=self.root/f"batch_{self.count}"))

    def remap(self,packets,prior,reviewer="Assistant A",aliases=(),instructions=None):
        self.count+=1;packet=self.root/f"target_{self.count}.jsonl";review.write_lines(packet,packets)
        return self.call(batches.remap,SimpleNamespace(packet=packet,instructions=instructions or self.instructions,
            reviewer=reviewer,alias=list(aliases),batch=prior,output=self.root/f"remap_{self.count}"))

    def test_packet_builder_is_byte_content_identical_to_actual_analyzer_function(self):
        references={"memory_catalog":[{"id":"mem_"+"1"*32,"canonical_text":"Your fictional album is Leafglass.","profile_id":"main","final_state":"active"},
            {"id":"mem_"+"2"*32,"canonical_text":"Your old album was green.","profile_id":"main","final_state":"superseded"},
            {"id":"mem_"+"3"*32,"canonical_text":"Your neighbor has a red album.","profile_id":"neighbor","final_state":"active"}],
            "cases":{"question":{"answerability":"known_authorized","authorization_expected":True,"rubric":self.packet()["rubric"]},
                     "denied":{"answerability":"unauthorized","authorization_expected":False,"rubric":{"required_semantic_claims":["Decline."]}}}}
        def row(slot,status="ok",case="question"):
            return {"case":{"id":case,"profile_id":"main","prompt":"What is my fictional album called?"},"slot":slot,
                "status":status,"response":{"speech":"Your album is Leafglass."},"model":"hidden-model","policy":"hidden-policy"}
        rows=[row(1),row(2),row(3,"interrupted"),row(4,case="denied")]
        original_ast=ast.parse(batches.ANALYZER.read_text())
        selected=ast.Module(body=[node for node in original_ast.body if isinstance(node,ast.FunctionDef)
                                 and node.name in ("blind_packets","observe_key","canonical")],type_ignores=[])
        namespace={"json":json,"defaultdict":defaultdict,"random":random,"re":re,"PACKET_FIELDS":review.PACKET_FIELDS}
        exec(compile(selected,str(batches.ANALYZER),"exec"),namespace)
        expected=namespace["blind_packets"](rows,references,87923)
        actual=batches.blind_packets(rows,references,87923)
        self.assertEqual(actual,expected)
        self.assertEqual(len(actual[0]),3)
        denied=next(item for item in actual[0] if item["answerability"]=="unauthorized")
        self.assertEqual(denied["reference_facts_without_ids"],[])
        self.assertIsNone(next(item for item in actual[0] if item["delivery_status"]=="not_delivered")["answer"])
        self.assertNotIn("hidden-model",review.canonical(actual[0]));self.assertNotIn("hidden-policy",review.canonical(actual[0]))

    def test_exact_public_content_remaps_id_preserving_original_and_rationale(self):
        original=self.packet();judgment=self.judgment(original,rationale="Exact original rationale.")
        prior=self.frozen_batch([original],[judgment]);final=self.packet(90)
        mapped=self.remap([final],[prior])
        self.assertEqual(review.read(mapped/"remap.json")["missing_groups"],0)
        self.assertEqual(review.lines(mapped/"reused_reviews.jsonl"),[{**judgment,"review_id":final["review_id"]}])
        self.assertEqual((prior/"original_reviews.jsonl").read_bytes(),(mapped/"original_batches/batch_000/original_reviews.jsonl").read_bytes())
        completed=self.call(batches.assemble,SimpleNamespace(remap=mapped,missing_review=None,output=self.root/"complete"))
        metadata,packet,values=batches.load_batch(completed)
        self.assertEqual(packet,{final["review_id"]:final});self.assertEqual(values[final["review_id"]]["rationale"],judgment["rationale"])
        self.assertEqual(metadata["reviewer"],"Assistant A")
        self.assertIs(review.read(completed/"provenance.json")["private_mapping_read"],False)

    def test_any_changed_public_content_remains_missing_and_requires_frozen_judgments(self):
        prior=self.frozen_batch([self.packet()])
        changed=[self.packet(10,prompt="What is my basket called?"),self.packet(11,answer="A different answer."),
            self.packet(12,delivery_status="not_delivered",answer=None),self.packet(13,answerability="unknown"),
            self.packet(14,rubric={"required_semantic_claims":["Different required answer."]}),
            self.packet(15,reference_facts_without_ids=["Your fictional album is Cloudglass."])]
        mapped=self.remap(changed,[prior]);missing=review.lines(mapped/"missing_packet.jsonl")
        self.assertEqual(len(missing),6);self.assertEqual(review.lines(mapped/"reused_reviews.jsonl"),[])
        with self.assertRaisesRegex(ValueError,"explicit frozen review"):
            batches.assemble(SimpleNamespace(remap=mapped,missing_review=None,output=self.root/"must_not_exist"),[])
        judgments=[self.judgment(item,label="technical_failure" if item["delivery_status"]=="not_delivered" else "partial") for item in missing]
        frozen=self.frozen_batch(missing,judgments)
        completed=self.call(batches.assemble,SimpleNamespace(remap=mapped,missing_review=frozen,output=self.root/"finished"))
        self.assertEqual(len(batches.load_batch(completed)[2]),6)

    def test_conflicting_prior_score_vectors_cannot_be_automatically_selected(self):
        first=self.frozen_batch([self.packet()]);second=self.frozen_batch([self.packet(2)],[self.judgment(self.packet(2),label="partial")])
        mapped=self.remap([self.packet(10)],[first,second])
        self.assertEqual(review.read(mapped/"remapping.json")[0]["status"],"conflicting_prior_score_vectors")
        self.assertEqual(review.lines(mapped/"reused_reviews.jsonl"),[])
        self.assertEqual(len(review.lines(mapped/"missing_packet.jsonl")),1)

    def test_same_scores_different_rationale_preserve_first_with_both_sources(self):
        first=self.frozen_batch([self.packet()],[self.judgment(self.packet(),rationale="First rationale.")])
        second=self.frozen_batch([self.packet(2)],[self.judgment(self.packet(2),rationale="Second rationale.")])
        mapped=self.remap([self.packet(10)],[first,second]);mapping=review.read(mapped/"remapping.json")[0]
        self.assertEqual(len(mapping["prior_candidates"]),2)
        self.assertEqual(review.lines(mapped/"reused_reviews.jsonl")[0]["rationale"],"First rationale.")

    def test_other_reviewer_and_changed_instructions_are_rejected(self):
        prior=self.frozen_batch([self.packet()],reviewer="Assistant B")
        with self.assertRaisesRegex(ValueError,"unapproved reviewer"):
            self.remap([self.packet(2)],[prior])
        own=self.frozen_batch([self.packet()]);changed=self.root/"changed.md";changed.write_text("Different instruction")
        with self.assertRaisesRegex(ValueError,"instruction bytes changed"):
            self.remap([self.packet(3)],[own],instructions=changed)

    def test_identity_aliases_are_explicit_and_preserved(self):
        prior=self.frozen_batch([self.packet()],reviewer="  Agent A initial  ")
        mapped=self.remap([self.packet(2)],[prior],reviewer="Agent A",aliases=["Agent A initial"])
        self.assertEqual(review.read(mapped/"remap.json")["identity_aliases"],["Agent A","Agent A initial"])

    def test_unfrozen_missing_packet_identity_change_rejected(self):
        mapped=self.remap([self.packet(2)],[])
        wrong=self.frozen_batch([self.packet(3)])
        with self.assertRaisesRegex(ValueError,"packet differs"):
            batches.assemble(SimpleNamespace(remap=mapped,missing_review=wrong,output=self.root/"bad"),[])

    def test_assembly_recomputes_reuse_from_originals_even_for_resealed_input(self):
        prior=self.frozen_batch([self.packet()]);mapped=self.remap([self.packet(2)],[prior])
        changed=self.root/"resealed";review.copy_sealed_directory(mapped,changed)
        (changed/"seal.json").unlink()
        values=review.lines(changed/"reused_reviews.jsonl");values[0]["label"]="partial"
        (changed/"reused_reviews.jsonl").write_text(review.canonical(values[0])+"\n");review.seal(changed)
        with self.assertRaisesRegex(ValueError,"differ from frozen originals"):
            batches.assemble(SimpleNamespace(remap=changed,missing_review=None,output=self.root/"tampered"),[])

    def test_known_abstention_and_identifier_leaks_reject_before_freezing(self):
        value=self.packet()
        with self.assertRaisesRegex(ValueError,"missed task"):
            self.frozen_batch([value],[self.judgment(value,label="appropriate_abstention",abstained=True)])
        with self.assertRaisesRegex(ValueError,"explicit evidence"):
            review.packet_index([self.packet(prompt="Recall mem_"+"f"*32)])

    def test_authoritative_catalog_excludes_expired_wrongprofile_and_superseded(self):
        freeze=self.root/"fakefreeze";prepared=freeze/"prepared_snapshot";prepared.mkdir(parents=True)
        seed={"profile_id":"main","evaluation_at":"2026-11-06T12:00:00Z","retention_days":30}
        record=lambda index:{"id":str(index),"canonical_text":f"Current fictional fact {index}.","status":"active","consent_status":"confirmed",
            "valid_from":"2026-11-01T12:00:00Z","valid_until":None,"retention_until":None,"created_at":"2026-11-01T12:00:00Z"}
        records=[record(index) for index in range(23)]
        extras=[dict(record(50),valid_until="2026-11-05T12:00:00Z"),dict(record(51),status="superseded")]
        review.write(prepared/"setup.json",{"details":{"profiles":[{"profile_id":"main","records":records+extras},
                                                                   {"profile_id":"neighbor","records":[record(60)]}]}})
        refs={"memory_catalog":[{"id":value["id"],"canonical_text":value["canonical_text"],"profile_id":"main","final_state":"active"} for value in records]}
        batches.verify_truth_catalog(freeze,{"memory_seed":seed},refs)
        refs["memory_catalog"][0]["canonical_text"]="Wrong fact text."
        with self.assertRaisesRegex(ValueError,"authoritative"):
            batches.verify_truth_catalog(freeze,{"memory_seed":seed},refs)

    def test_export_real_sealed157_prefix_without_runtime_or_numpy_imports(self):
        imports_before=set(sys.modules)
        from tests.test_retrieval_continuation import ContinuationTests
        fixture=ContinuationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        for case in fixture.cases:case.update(profile_id="main",consent_authorized=True)
        seed={"profile_id":"main","evaluation_at":"2026-11-06T12:00:00Z","retention_days":30}
        records=[{"id":str(index),"canonical_text":f"Current fictional fact {index}.","status":"active","consent_status":"confirmed",
            "valid_from":"2026-11-01T12:00:00Z","valid_until":None,"retention_until":None,"created_at":"2026-11-01T12:00:00Z"} for index in range(23)]
        review.write(fixture.freeze/"prepared_snapshot/setup.json",{"details":{"profiles":[{"profile_id":"main","records":records}]}})
        refs={"memory_catalog":[{"id":record["id"],"canonical_text":record["canonical_text"],"profile_id":"main","final_state":"active"} for record in records],
              "cases":{case["id"]:{"answerability":"known_authorized","authorization_expected":True,"rubric":self.packet()["rubric"]} for case in fixture.cases}}
        (fixture.freeze/"runtime.json").write_text(json.dumps({"execution_cases":fixture.cases,"memory_seed":seed}))
        review.write(fixture.freeze/"references.json",refs)
        fixture.frozen.update(source_sha256={},runtime_sha256=review.digest(fixture.freeze/"runtime.json"),
            references_sha256=review.digest(fixture.freeze/"references.json"),planned_attempts=864)
        (fixture.freeze/"freeze.json").write_text(json.dumps(fixture.frozen));review.seal(fixture.freeze)
        def delivered(values):
            for row in values["observations.jsonl"]:
                row["response"]={"speech":"Your album is Leafglass." if row["status"]=="ok" else "Undelivered raw answer must remain hidden."}
        entries=[fixture.fragment(slot,48,delivered) for slot in range(1,4)]+[fixture.fragment(4,13,delivered)]
        run=fixture.root/"run";run.mkdir()
        review.write(run/"plan.json",{"freeze_sha256":review.digest(fixture.freeze/"freeze.json"),"schedule":fixture.schedule})
        review.write(run/"batch_finish.json",{"status":"interrupted","source_unchanged":True,"sessions":entries,"rejected_sessions":[]})
        review.seal(run)
        output=self.call(batches.export,SimpleNamespace(freeze=fixture.freeze,run=run,output=self.root/"export"))
        packets=review.lines(output/"blinded/packet_a.jsonl")
        self.assertEqual(len(packets),49)
        self.assertEqual(review.read(output/"private/cohort.json")["attempted"],157)
        self.assertEqual(sum(len(item["observation_keys"]) for item in review.read(output/"private/mapping.json")),157)
        self.assertNotIn("Undelivered raw answer",review.canonical(packets))
        self.assertEqual((output/"blinded/REVIEW_INSTRUCTIONS.md").read_text(),batches.instructions_from_source())
        self.assertNotIn("numpy",set(sys.modules)-imports_before)


if __name__=="__main__":unittest.main()
