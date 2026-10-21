import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.rag.citations import StatuteEvidence
from legal_rag.rag.pipeline import AnswerStatus, GroundedAnswer
from scripts.evaluate_end_to_end_rag import aggregate, audit_rendered_answer


class EndToEndEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = json.loads((ROOT / "data/evaluation/end_to_end_cases.json").read_text(encoding="utf-8"))

    def test_dataset_has_ten_questions_and_two_refusals_per_domain(self):
        self.assertEqual(Counter(x["category"] for x in self.items), {
            "labor": 10, "housing_lease": 10, "inheritance": 10,
        })
        refusals = Counter(x["category"] for x in self.items if not x["expected_answerable"])
        self.assertEqual(refusals, {"labor": 2, "housing_lease": 2, "inheritance": 2})
        self.assertEqual(len({x["id"] for x in self.items}), 30)

    def test_answer_audit_detects_claim_without_known_citation(self):
        source = StatuteEvidence(1, "x", "근로기준법", "제27조", "", "원문", "https://law.go.kr/x")
        answer = GroundedAnswer(
            AnswerStatus.ANSWERED,
            "## 안내\n\n근거 있는 주장 [근거 1]\n\n### 다음 행동\n\n- 근거 없는 주장",
            (source,), 1,
        )
        audit = audit_rendered_answer(answer)
        self.assertEqual(audit["claim_count"], 2)
        self.assertEqual(audit["ungrounded_claim_count"], 1)
        self.assertFalse(audit["citation_valid"])

    def test_partial_aggregate_allows_no_refusal_items_yet(self):
        result = {
            "expected_answerable": True, "answered": True, "correct_refusal": False,
            "citation_audit": {"citation_valid": True}, "safe_grounding_behavior": True,
            "expected_case_cited": True, "status": "answered",
        }
        metrics = aggregate([result])
        self.assertEqual(metrics["answer_success_rate"], 1.0)
        self.assertIsNone(metrics["refusal_accuracy"])

    def test_saved_optimized_result_has_no_ungrounded_exposure(self):
        path = ROOT / "data/evaluation/end_to_end_results_optimized.json"
        results = json.loads(path.read_text(encoding="utf-8"))["results"]
        self.assertEqual(len(results), 30)
        self.assertTrue(all(x["safe_grounding_behavior"] for x in results))
        answered = [x for x in results if x["answered"]]
        self.assertTrue(answered)
        self.assertTrue(all(x["citation_audit"]["citation_valid"] for x in answered))

    def test_saved_final_result_keeps_safety_and_improves_answer_success(self):
        payload = json.loads(
            (ROOT / "data/evaluation/end_to_end_results_final.json").read_text(encoding="utf-8")
        )
        results = payload["results"]
        metrics = payload["metrics"]
        self.assertEqual(len(results), 30)
        self.assertGreaterEqual(metrics["answer_success_rate"], 0.75)
        self.assertEqual(metrics["citation_accuracy"], 1.0)
        self.assertEqual(metrics["ungrounded_claim_block_rate"], 1.0)
        self.assertEqual(metrics["refusal_accuracy"], 1.0)
        self.assertTrue(all(x["safe_grounding_behavior"] for x in results))


if __name__ == "__main__": unittest.main()
