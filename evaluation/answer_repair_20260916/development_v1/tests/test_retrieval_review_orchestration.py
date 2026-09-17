"""Tiny stdlib-only structural tests; all examples are synthetic judgments."""
from contextlib import redirect_stdout
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import reconcile_independent_retrieval_reviews as reviews


def identifier(number):return "review_"+f"{number:032x}"


def packet(number,answerability="known_authorized"):
    return {"review_id":identifier(number),"prompt":"What is my fictional album called?",
        "answer":"Your album is Leafglass.","delivery_status":"delivered","answerability":answerability,
        "rubric":{"required_semantic_claims":["The album is Leafglass."]},
        "reference_facts_without_ids":["Your album is Leafglass."]}


def judgment(number,label="complete",rationale="It supplies the requested fact.",**flags):
    return {"review_id":identifier(number),"label":label,"rationale":rationale,
            **{flag:False for flag in reviews.FLAGS},**flags}


class ReviewOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.packet_path=self.root/"packet.jsonl"
        self.packets=[packet(1),packet(2,"unknown")]
        reviews.write_lines(self.packet_path,self.packets)
        self.instructions=self.root/"instructions.md";self.instructions.write_text("Fictional structural test instructions.\n")
        self.first,self.second=self.root/"first.jsonl",self.root/"second.jsonl"
        # Preserve unusual whitespace/newline formatting to test exact copies.
        self.first.write_text(json.dumps(judgment(1),indent=2).replace("\n","")+"\n"+
                              json.dumps(judgment(2,"partial"))+"\n")
        reviews.write_lines(self.second,[judgment(1,rationale="Different explanation, same judgments."),
                                         judgment(2,"incorrect")])

    def command(self,args):
        with redirect_stdout(io.StringIO()):reviews.main([str(arg) for arg in args])

    def compare(self):
        output=self.root/"comparison"
        self.command(["compare","--packet",self.packet_path,"--instructions",self.instructions,
            "--review-a",self.first,"--review-b",self.second,"--reviewer-a","fresh assistant alpha",
            "--reviewer-b","fresh assistant beta","--output",output])
        return output

    def resolve(self,comparison):
        adjudication=self.root/"third.jsonl"
        reviews.write_lines(adjudication,[judgment(2,"appropriate_abstention",abstained=True)])
        output=self.root/"resolution"
        self.command(["resolve","--comparison",comparison,"--adjudication",adjudication,
            "--adjudicator","fresh assistant gamma","--output",output])
        return output

    def test_comparison_preserves_exact_originals_and_ignores_rationale_only_difference(self):
        output=self.compare();reviews.verify_seal(output)
        self.assertEqual((output/"original_review_a.jsonl").read_bytes(),self.first.read_bytes())
        self.assertEqual((output/"original_review_b.jsonl").read_bytes(),self.second.read_bytes())
        result=reviews.read(output/"comparison.json")
        self.assertEqual((result["total_groups"],result["agreement_count"],result["disagreement_count"]),(2,1,1))
        self.assertIsNone(result["mapping_coverage_complete"])
        disagreement=reviews.lines(output/"disagreement_packet.jsonl")
        self.assertEqual(len(disagreement),1)
        self.assertEqual(disagreement[0]["review_id"],identifier(2))
        self.assertEqual(set(disagreement[0]),reviews.PACKET_FIELDS|{"proposed_judgments"})
        self.assertTrue(all(set(j)==reviews.REVIEW_FIELDS-{"review_id"} for j in disagreement[0]["proposed_judgments"]))
        self.assertNotIn("fresh assistant",json.dumps(disagreement))

    def test_resolution_uses_only_agreed_original_or_supplied_third_judgment(self):
        comparison=self.compare();output=self.resolve(comparison);reviews.verify_seal(output)
        resolved={r["review_id"]:r for r in reviews.lines(output/"resolved_reviews.jsonl")}
        original={r["review_id"]:r for r in reviews.lines(self.first)}
        self.assertEqual(resolved[identifier(1)],original[identifier(1)])
        self.assertEqual(resolved[identifier(2)]["label"],"appropriate_abstention")
        agreement=reviews.read(output/"review_agreement.json")
        self.assertEqual(agreement["adjudicated_count"],1)
        self.assertIsNone(agreement["mapping_coverage_complete"])
        self.assertFalse(agreement["mapping_read"])
        self.assertEqual(agreement["human_validation"],"pending")

    def test_resolution_rejects_missing_or_wrong_disagreement_ids(self):
        comparison=self.compare();third=self.root/"wrong.jsonl"
        reviews.write_lines(third,[judgment(1)])
        with self.assertRaisesRegex(ValueError,"unknown review ID"):
            self.command(["resolve","--comparison",comparison,"--adjudication",third,
                "--adjudicator","fresh gamma","--output",self.root/"bad"])
        self.assertFalse((self.root/"bad").exists())

    def test_reviewer_and_adjudicator_distinctness_uses_normalized_identity(self):
        with self.assertRaisesRegex(ValueError,"distinct reviewer"):
            self.command(["compare","--packet",self.packet_path,"--instructions",self.instructions,
                "--review-a",self.first,"--review-b",self.second,"--reviewer-a","same identity",
                "--reviewer-b"," same identity ","--output",self.root/"bad-identities"])
        comparison=self.compare();third=self.root/"third-for-identity.jsonl"
        reviews.write_lines(third,[judgment(2,"appropriate_abstention",abstained=True)])
        with self.assertRaisesRegex(ValueError,"third reviewer"):
            self.command(["resolve","--comparison",comparison,"--adjudication",third,
                "--adjudicator"," fresh assistant alpha ","--output",self.root/"bad-third"])

    def test_resolution_recomputes_summary_counts_and_agreed_ids(self):
        comparison=self.compare()
        altered=self.root/"manually-sealed-comparison"
        altered.mkdir()
        for path in comparison.rglob("*"):
            if path.is_file() and path!=comparison/"seal.json":
                destination=altered/path.relative_to(comparison)
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(path.read_bytes())
        summary=reviews.read(altered/"comparison.json")
        summary["agreement_count"]=0;summary["agreed_review_ids"]=[]
        (altered/"comparison.json").write_text(json.dumps(summary))
        reviews.seal(altered)
        with self.assertRaisesRegex(ValueError,"summary differs"):
            self.command(["resolve","--comparison",altered,"--output",self.root/"bad-summary"])

    def test_known_general_and_flag_validation_match_shared_rubric(self):
        for answerability in ("known_authorized","self_contained_general"):
            lookup=reviews.packet_index([packet(1,answerability)])
            with self.assertRaisesRegex(ValueError,"missed task"):
                reviews.review_index([judgment(1,"appropriate_abstention",abstained=True)],lookup)
        lookup=reviews.packet_index([packet(1,"unknown")])
        with self.assertRaisesRegex(ValueError,"abstained=true"):
            reviews.review_index([judgment(1,"appropriate_abstention")],lookup)
        with self.assertRaisesRegex(ValueError,"unsupported_claim=true"):
            reviews.review_index([judgment(1,"incorrect",unsupported_personal_claim=True)],lookup)

    def test_reviewed_analysis_binding_preserves_exact_resolved_judgments_and_source_digest(self):
        analysis=self.root/"binding";analysis.mkdir()
        packet_lookup=reviews.packet_index([packet(1)])
        resolved=reviews.review_index([judgment(1)],packet_lookup)
        self.assertFalse(reviews.verify_reviewed_analysis_binding(analysis,resolved,packet_lookup,"sourcehash"))
        reviews.write_lines(analysis/"resolved_reviews.jsonl",[judgment(1)])
        reviews.write(analysis/"provenance.json",{"reviews_sha256":"sourcehash"})
        self.assertTrue(reviews.verify_reviewed_analysis_binding(analysis,resolved,packet_lookup,"sourcehash"))
        with self.assertRaisesRegex(ValueError,"source judgment digest differs"):
            reviews.verify_reviewed_analysis_binding(analysis,resolved,packet_lookup,"otherhash")
        (analysis/"resolved_reviews.jsonl").write_text(json.dumps(judgment(1,"partial"))+"\n")
        with self.assertRaisesRegex(ValueError,"judgments differ"):
            reviews.verify_reviewed_analysis_binding(analysis,resolved,packet_lookup,"sourcehash")

    def test_mapping_is_checked_only_after_sealed_resolution_and_covers_each_attempt(self):
        resolution=self.resolve(self.compare())
        analysis=self.root/"analysis";analysis.mkdir();(analysis/"blinded").mkdir();(analysis/"private").mkdir()
        reviews.copy_exact(self.packet_path,analysis/"blinded/packet_a.jsonl")
        reviews.write(analysis/"audit.json",{"valid":True,"observed_attempts":3,"planned_attempts":3})
        reviews.write(analysis/"private/mapping.json",[
            {"review_id":identifier(1),"case_id":"case-a","observation_keys":["slot1:a","slot2:a"]},
            {"review_id":identifier(2),"case_id":"case-b","observation_keys":["slot3:b"]}])
        with (analysis/"attempts.csv").open("w",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=["observation_key","review_id","case_id"]);writer.writeheader()
            for key,number,case in (("slot1:a",1,"case-a"),("slot2:a",1,"case-a"),("slot3:b",2,"case-b")):
                writer.writerow({"observation_key":key,"review_id":identifier(number),"case_id":case})
        reviews.seal(analysis)
        output=self.root/"verified"
        self.command(["verify-mapping","--resolution",resolution,"--analysis",analysis,"--output",output])
        reviews.verify_seal(output)
        agreement=reviews.read(output/"review_agreement.json")
        self.assertTrue(agreement["mapping_coverage_complete"])
        self.assertEqual(agreement["mapped_observations"],3)
        self.assertTrue(agreement["planned_attempt_coverage_complete"])
        self.assertEqual((output/"resolved_reviews.jsonl").read_bytes(),(resolution/"resolved_reviews.jsonl").read_bytes())
        self.assertFalse((output/"private").exists())


if __name__=="__main__":unittest.main()
