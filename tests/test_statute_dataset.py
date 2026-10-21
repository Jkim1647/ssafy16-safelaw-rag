import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "processed" / "statutes.json"
MANIFEST = ROOT / "data" / "processed" / "statutes_manifest.json"


class StatuteDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = json.loads(DATASET.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_matches_dataset(self):
        self.assertEqual(self.manifest["document_count"], len(self.documents))
        self.assertEqual(
            self.manifest["category_counts"],
            dict(sorted(Counter(item["category"] for item in self.documents).items())),
        )
        self.assertEqual(
            self.manifest["dataset_sha256"],
            hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        )

    def test_documents_are_complete_and_unique(self):
        required = {
            "law_id",
            "category",
            "law_name",
            "article_no",
            "article_title",
            "text",
            "effective_date",
            "source_url",
            "source_law_id",
            "law_sequence",
            "law_key",
            "article_key",
        }
        identifiers = set()
        for item in self.documents:
            self.assertTrue(required.issubset(item))
            self.assertTrue(all(item[field] for field in required))
            self.assertEqual(urlparse(item["source_url"]).hostname, "www.law.go.kr")
            identifiers.add((item["category"], item["law_id"]))
        self.assertEqual(len(identifiers), len(self.documents))

    def test_dataset_contains_no_api_credential(self):
        serialized = DATASET.read_text(encoding="utf-8")
        self.assertNotIn('"OC"', serialized)
        self.assertNotIn("LAW_API_OC", serialized)


if __name__ == "__main__":
    unittest.main()
