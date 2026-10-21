import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.domain.models import PrecedentLevel
from legal_rag.security.source_policy import is_official_source


class CaseDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset_path = ROOT / "data" / "processed" / "cases.json"
        cls.manifest_path = ROOT / "data" / "processed" / "cases_manifest.json"
        cls.documents = json.loads(cls.dataset_path.read_text(encoding="utf-8"))
        cls.manifest = json.loads(cls.manifest_path.read_text(encoding="utf-8"))

    def test_documents_keep_auditable_precedent_metadata(self):
        self.assertTrue(self.documents)
        self.assertEqual(
            len({(item["category"], item["case_number"]) for item in self.documents}),
            len(self.documents),
        )
        allowed_levels = {item.value for item in PrecedentLevel}
        for item in self.documents:
            self.assertTrue(item["case_name"])
            self.assertTrue(item["case_type"])
            self.assertTrue(item["decision_type"])
            self.assertIn(item["precedent_level"], allowed_levels)
            self.assertIsInstance(item["cited_cases"], list)
            self.assertTrue(is_official_source(item["source_url"]))

    def test_manifest_matches_dataset_and_marks_expert_review_status(self):
        digest = hashlib.sha256(self.dataset_path.read_bytes()).hexdigest()
        self.assertEqual(self.manifest["schema_version"], 3)
        self.assertEqual(self.manifest["dataset_sha256"], digest)
        self.assertEqual(self.manifest["document_count"], len(self.documents))
        self.assertEqual(
            self.manifest["precedent_level_counts"],
            dict(sorted(Counter(item["precedent_level"] for item in self.documents).items())),
        )
        self.assertIn("미검수", self.manifest["review_status"])

    def test_dataset_does_not_contain_api_credentials(self):
        serialized = self.dataset_path.read_text(encoding="utf-8")
        self.assertNotIn("LAW_API_OC", serialized)
        self.assertNotIn('"OC"', serialized)


if __name__ == "__main__":
    unittest.main()
