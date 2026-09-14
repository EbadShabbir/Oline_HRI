"""Small offline tests of blinding and dependent paired accounting."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import analyze_independent_retrieval as analysis


class RetrievalExperimentAnalysisTests(unittest.TestCase):
    def references(self):
        return {"memory_catalog":[{"id":"mem_"+"1"*32,"canonical_text":"Your fictional album is Leafglass.",
                                   "profile_id":"fictional-profile","final_state":"active"},
                                  {"id":"mem_"+"2"*32,"canonical_text":"Your fictional basket is blue.",
                                   "profile_id":"fictional-profile","final_state":"active"},
                                  {"id":"mem_"+"3"*32,"canonical_text":"Your old basket was green.",
                                   "profile_id":"fictional-profile","final_state":"superseded"},
                                  {"id":"mem_"+"4"*32,"canonical_text":"Your neighbor is Keld.",
                                   "profile_id":"different-profile","final_state":"active"}],
            "cases":{"case-a":{"answerability":"known_authorized","authorization_expected":True,"relevant_evidence_ids":["mem_"+"1"*32],
                "rubric":{"required_semantic_claims":["The album is Leafglass."]}},
                     "case-b":{"answerability":"unknown","authorization_expected":True,"relevant_evidence_ids":[],
                "rubric":{"required_semantic_claims":["Do not invent a name."]}}}}

    def raw(self, case="case-a", slot=1, answer="Your album is Leafglass.", status="ok"):
        row={"case":{"id":case,"profile_id":"fictional-profile","prompt":"What is my album called?"},"slot":slot,
             "status":status,"model":"secret-model","policy":"secret-policy","wall_ns":17}
        if answer is not None:row["response"]={"speech":answer}
        return row

    def test_blinding_groups_exact_case_answer_status_without_identity(self):
        rows=[self.raw(slot=1),self.raw(slot=2),self.raw(case="case-b",slot=3),
              self.raw(slot=4,answer=None,status="error")]
        packet,second,mapping=analysis.blind_packets(rows,self.references(),87237)
        self.assertEqual(len(packet),3)
        self.assertEqual({p["review_id"] for p in packet},{p["review_id"] for p in second})
        self.assertEqual(sorted(len(m["observation_keys"]) for m in mapping),[1,1,2])
        self.assertEqual({k for m in mapping for k in m["observation_keys"]},
                         {analysis.observe_key(r) for r in rows})
        for item in packet:
            self.assertEqual(set(item),analysis.PACKET_FIELDS)
            encoded=json.dumps(item)
            for forbidden in ("secret-model","secret-policy","wall_ns","mem_","observation_keys"):
                self.assertNotIn(forbidden,encoded)
        self.assertEqual((packet,second,mapping),analysis.blind_packets(rows,self.references(),87237))

    def test_full_current_authorized_truth_is_shared_and_denied_background_is_empty(self):
        refs=self.references()
        packets,_,_=analysis.blind_packets([self.raw(),self.raw(case="case-b",slot=2)],refs,17)
        expected=["Your fictional album is Leafglass.","Your fictional basket is blue."]
        self.assertTrue(all(p["reference_facts_without_ids"]==expected for p in packets))
        refs["cases"]["case-b"]["authorization_expected"]=False
        packets,_,_=analysis.blind_packets([self.raw(case="case-b")],refs,17)
        self.assertEqual(packets[0]["reference_facts_without_ids"],[])

    def test_failed_partial_raw_output_is_not_presented_as_delivered(self):
        rows=[self.raw(status="error",answer="Undelivered hallucination"),
              self.raw(status="error",slot=2,answer="Different undelivered raw output")]
        packet,_,mapping=analysis.blind_packets(rows,self.references(),61)
        self.assertEqual(len(packet),1)
        self.assertIsNone(packet[0]["answer"])
        self.assertEqual(packet[0]["delivery_status"],"not_delivered")
        self.assertEqual(len(mapping[0]["observation_keys"]),2)

    def test_reviews_cannot_reward_known_fact_abstention_or_duplicate_groups(self):
        packet,_,_=analysis.blind_packets([self.raw()],self.references(),65)
        value={"review_id":packet[0]["review_id"],"label":"complete","rationale":"Supplies the answer.",
               **{flag:False for flag in analysis.FLAGS}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"review.jsonl"
            path.write_text(json.dumps(value)+"\n")
            self.assertEqual(len(analysis.load_judgments(path,packet)),1)
            value["label"]="appropriate_abstention";value["abstained"]=True
            path.write_text(json.dumps(value)+"\n")
            with self.assertRaisesRegex(ValueError,"known authorized"):
                analysis.load_judgments(path,packet)
            value["label"]="inappropriate_abstention"
            path.write_text(json.dumps(value)+"\n")
            self.assertEqual(len(analysis.load_judgments(path,packet)),1)
            path.write_text((json.dumps(value)+"\n")*2)
            with self.assertRaisesRegex(ValueError,"uniquely cover"):
                analysis.load_judgments(path,packet)

    def test_general_abstention_is_failure_and_abstention_flag_is_required(self):
        packet,_,_=analysis.blind_packets([self.raw()],self.references(),65)
        packet[0]["answerability"]="self_contained_general"
        value={"review_id":packet[0]["review_id"],"label":"appropriate_abstention","rationale":"Declines answer.",
               **{flag:False for flag in analysis.FLAGS}}
        value["abstained"]=True
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"review.jsonl";path.write_text(json.dumps(value)+"\n")
            with self.assertRaisesRegex(ValueError,"self-contained general"):
                analysis.load_judgments(path,packet)
            value["label"]="inappropriate_abstention";value["abstained"]=False
            path.write_text(json.dumps(value)+"\n")
            with self.assertRaisesRegex(ValueError,"require the abstained flag"):
                analysis.load_judgments(path,packet)

    def test_unsupported_personal_flag_requires_parent_flag(self):
        packet,_,_=analysis.blind_packets([self.raw()],self.references(),65)
        value={"review_id":packet[0]["review_id"],"label":"incorrect","rationale":"Invents detail.",
               **{flag:False for flag in analysis.FLAGS}}
        value["unsupported_personal_claim"]=True
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"review.jsonl";path.write_text(json.dumps(value)+"\n")
            with self.assertRaisesRegex(ValueError,"also be an unsupported"):
                analysis.load_judgments(path,packet)

    def test_paired_repetitions_average_before_whole_scenario_bootstrap(self):
        rows=[]
        for model in analysis.MODELS:
            for scenario in range(8):
                for policy,offset in (("OFF",0),("ALWAYS",1),("SELECTIVE",2)):
                    for rep in (1,2,3):
                        rows.append({"model":model,"policy":policy,"case_id":str(scenario),
                            "scenario_id":str(scenario),"category":"category-a","repetition":rep,
                            "request_s":100*rep+scenario+offset,"failure":False,"task_success":policy!="OFF"})
        with patch.object(analysis,"BOOTSTRAP_REPLICATES",25):
            pairs,means,summary=analysis.paired_analysis(rows)
        selected=next(s for s in summary if s["model"]==analysis.MODELS[0] and s["comparison"]=="SELECTIVE-ALWAYS" and s["category"]=="overall")
        self.assertEqual(selected["paired_attempts"],24)
        self.assertEqual(selected["paired_requests"],8)
        self.assertEqual(selected["quality_pairs"],{"both_success":24})
        self.assertEqual(selected["differences"]["request_s_difference"]["mean"],1)
        self.assertEqual(selected["differences"]["request_s_difference"]["bootstrap_95_low"],1)
        self.assertTrue(all(m["paired_repetitions"]==3 for m in means))

    def test_request_means_include_metric_present_only_after_first_repetition(self):
        rows=[]
        for policy,coverage in (("OFF",0),("SELECTIVE",1)):
            for rep in (1,2,3):
                rows.append({"model":analysis.MODELS[0],"policy":policy,"case_id":"a",
                    "scenario_id":"a","category":"category-a","repetition":rep,"request_s":rep,
                    "supplied_coverage":None if rep==1 else coverage})
        with patch.object(analysis,"BOOTSTRAP_REPLICATES",25):
            _,means,_=analysis.paired_analysis(rows)
        selected=next(m for m in means if m["comparison"]=="SELECTIVE-OFF")
        self.assertEqual(selected["supplied_coverage_difference"],1)

    def test_seal_covers_file_set_and_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"artifact";path.mkdir();(path/"data.json").write_text("{}");analysis.seal(path)
            analysis.verify_seal(path)
            path.chmod(0o700);(path/"data.json").chmod(0o600);(path/"data.json").write_text("changed")
            with self.assertRaisesRegex(ValueError,"sealed contents differ"):
                analysis.verify_seal(path)

    def rejection(self,path,*,called=False,claimed_attempts=0):
        path.mkdir()
        slot={"slot":1,"model":analysis.MODELS[0],"policy":"OFF","repetition":1,"request_ids":["a"]}
        policy={"min_start_available_kib":2048*1024,"max_start_swap_used_kib":3600000,
                "max_start_temperature_c_exclusive":55}
        state={"resident_models":[],"boot_id":"fixedboot","thermal_trip_events":{"cpu":0},
               "power_mode":"15W mode 0","memory":{"swap_total_kib":3901608,"swap_used_kib":1000,
               "mem_available_kib":1800*1024},"temperatures_c":{"cpu":50}}
        manifest={"slot":slot,"freeze_sha256":"freezehash","device_policy":policy,
                  "config":{"ollama":{k:analysis.MODELS[0] for k in
                    ("small_model","general_large_model","large_model")}}}
        summary={"attempted":claimed_attempts,"planned":48,"status":"interrupted","cleanup_errors":[],
            "session_wall_ns":2_000_000_000,"failure":{"type":"SafetyGateError",
                "message":"available memory is below the revised 2 GiB start gate"}}
        for name,value in (("manifest.json",manifest),("summary.json",summary),("start.json",state),("finish.json",state)):
            (path/name).write_text(json.dumps(value))
        if called:(path/"http_calls.jsonl").write_text('{"event":"http_start","endpoint":"/api/chat"}\n')
        analysis.seal(path)
        return slot,{"device_policy":policy}

    def test_rejected_resource_admission_is_preserved_separately_and_proves_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"rejected";slot,frozen=self.rejection(path)
            errors=[];row=analysis.audit_rejected_session(path,slot,frozen,"freezehash",errors)
            self.assertEqual(errors,[])
            self.assertEqual(row["attempted"],0)
            self.assertEqual(row["worker_session_wall_s"],2)
            self.assertEqual(row["http_events"],0)
            self.assertEqual(row["seal_sha256"],analysis.digest(path/"seal.json"))
            path=Path(tmp)/"called";slot,frozen=self.rejection(path,called=True)
            errors=[];analysis.audit_rejected_session(path,slot,frozen,"freezehash",errors)
            self.assertTrue(any("observations or calls" in e for e in errors))

    def test_rejected_admission_must_have_zero_attempts_and_same_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"rejected";slot,frozen=self.rejection(path,claimed_attempts=1)
            errors=[];analysis.audit_rejected_session(path,slot,frozen,"otherfreeze",errors)
            self.assertTrue(any("attempted a scheduled request" in e for e in errors))
            self.assertTrue(any("freeze or slot differs" in e for e in errors))

    def test_admission_overhead_provenance_retains_prior_completed_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=Path(tmp)/"first";first.mkdir()
            (first/"plan.json").write_text(json.dumps({"freeze_sha256":"hash","continuation_from":None}))
            (first/"startup_waits.jsonl").write_text('{"event":"admission_complete","slot":1,"wall_ns":170}\n')
            analysis.seal(first)
            second=Path(tmp)/"second";second.mkdir()
            (second/"plan.json").write_text(json.dumps({"freeze_sha256":"hash","continuation_from":str(first)}))
            (second/"startup_waits.jsonl").write_text('{"event":"admission_complete","slot":2,"wall_ns":250}\n')
            analysis.seal(second)
            events,sources=analysis.admission_events(second,"hash")
            self.assertEqual([e["slot"] for e in events],[1,2])
            self.assertEqual(len(sources),2)


if __name__=="__main__":unittest.main()
