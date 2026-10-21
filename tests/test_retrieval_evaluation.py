import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.evaluate_statute_retrieval import aggregate


CASES = ROOT / "data" / "evaluation" / "statute_retrieval_cases.json"
STATUTES = ROOT / "data" / "processed" / "statutes.json"


class RetrievalEvaluationDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(CASES.read_text(encoding="utf-8"))
        cls.statutes = json.loads(STATUTES.read_text(encoding="utf-8"))

    def test_has_ten_unique_questions_per_domain(self):
        counts = Counter(item["category"] for item in self.cases)
        self.assertEqual(
            counts,
            {"labor": 10, "housing_lease": 10, "inheritance": 10},
        )
        self.assertEqual(len({item["id"] for item in self.cases}), 30)
        self.assertEqual(len({item["query"] for item in self.cases}), 30)

    def test_every_expected_article_exists_in_source_dataset(self):
        available = {
            (item["category"], item["law_name"], item["article_no"])
            for item in self.statutes
        }
        for case in self.cases:
            for expected in case["expected"]:
                key = (case["category"], expected["law_name"], expected["article_no"])
                self.assertIn(key, available, msg=f"평가 정답 조문 누락: {case['id']} {key}")

    def test_metric_aggregation_calculates_macro_average(self):
        results = [
            {"category": "labor", "recall_at_5": 1.0, "reciprocal_rank": 1.0, "hit_at_5": True},
            {"category": "labor", "recall_at_5": 0.0, "reciprocal_rank": 0.0, "hit_at_5": False},
        ]

        metrics = aggregate(results)

        self.assertEqual(metrics["labor"]["recall_at_5"], 0.5)
        self.assertEqual(metrics["labor"]["mrr"], 0.5)
        self.assertEqual(metrics["overall"]["hit_at_5"], 0.5)


if __name__ == "__main__":
    unittest.main()
