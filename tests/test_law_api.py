import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.collectors.law_api import (
    ArticleRange,
    LawOpenApiClient,
    StatuteSourceConfig,
    normalize_statutes,
)
from legal_rag.domain.models import LegalCategory


class FixtureTransport:
    def __init__(self):
        self.urls = []

    def __call__(self, url: str, timeout: float) -> bytes:
        self.urls.append(url)
        name = "law_search.json" if "lawSearch.do" in url else "law_body.json"
        return (ROOT / "tests" / "fixtures" / name).read_bytes()


class LawOpenApiClientTests(unittest.TestCase):
    def test_search_and_fetch_use_official_api(self):
        transport = FixtureTransport()
        client = LawOpenApiClient("secret-oc", transport=transport)

        result = client.search_current_law("근로기준법")
        law = client.fetch_current_law(result.source_law_id)

        self.assertEqual(result.source_law_id, "001872")
        self.assertEqual(law["기본정보"]["법령명_한글"], "근로기준법")
        self.assertEqual(len(transport.urls), 2)

    def test_normalizes_nested_article_structure(self):
        payload = json.loads((ROOT / "tests" / "fixtures" / "law_body.json").read_text(encoding="utf-8"))
        config = StatuteSourceConfig(
            law_name="근로기준법",
            category=LegalCategory.LABOR,
            issue_tags=("해고",),
            article_ranges=(ArticleRange(20, 30),),
        )

        documents = normalize_statutes(payload["법령"], config)

        self.assertEqual(len(documents), 1)
        document = documents[0]
        self.assertEqual(document.article_no, "제27조")
        self.assertIn("해고사유와 해고시기", document.text)
        self.assertIn("서면에는 해고사유", document.text)
        self.assertTrue(document.source_url.startswith("https://www.law.go.kr/"))

    def test_oc_is_not_stored_in_domain_document(self):
        transport = FixtureTransport()
        client = LawOpenApiClient("secret-oc", transport=transport)
        result = client.search_current_law("근로기준법")
        law = client.fetch_current_law(result.source_law_id)
        documents = normalize_statutes(
            law,
            StatuteSourceConfig("근로기준법", LegalCategory.LABOR),
        )

        self.assertNotIn("secret-oc", repr(documents))
        self.assertTrue(all("secret-oc" not in item.source_url for item in documents))


if __name__ == "__main__":
    unittest.main()
