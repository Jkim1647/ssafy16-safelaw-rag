import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.evaluate_case_retrieval import aggregate


class CaseRetrievalEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / "data/evaluation/case_retrieval_cases.json").read_text(encoding="utf-8"))
        cls.documents = json.loads((ROOT / "data/processed/cases.json").read_text(encoding="utf-8"))

    def test_has_exactly_ten_questions_per_domain(self):
        self.assertEqual(Counter(x["category"] for x in self.cases), {
            "labor": 10, "housing_lease": 10, "inheritance": 10,
        })
        self.assertEqual(len({x["id"] for x in self.cases}), 30)
        self.assertEqual(len({x["query"] for x in self.cases}), 30)

    def test_expected_and_acceptable_cases_exist_in_current_fifty(self):
        available = {(x["category"], x["case_number"]) for x in self.documents}
        for case in self.cases:
            for number in case["expected_case_numbers"] + case["acceptable_case_numbers"]:
                self.assertIn((case["category"], number), available, case["id"])

    def test_aggregate_includes_contamination(self):
        results = [{"category": "labor", "recall_at_5": 1.0, "reciprocal_rank": .5,
                    "hit_at_5": True, "contamination_at_5": .4}]
        self.assertEqual(aggregate(results)["overall"]["contamination_at_5"], .4)


if __name__ == "__main__":
    unittest.main()
