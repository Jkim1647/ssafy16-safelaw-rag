import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.collectors.court_cases import CaseSearchResult
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.case_enrichment import IncrementalCaseEnricher
from legal_rag.rag.retrieval import SearchPlan


class FakeClient:
    def __init__(self):
        self.search_calls = 0
        self.fetch_calls = 0

    def search(self, query, *, display=5):
        self.search_calls += 1
        return [CaseSearchResult("999", "2099다1", "부당해고", "대법원", date(2099, 1, 1), "판결", "대법원")]

    def fetch(self, case_id):
        self.fetch_calls += 1
        return {"판례정보일련번호": "999", "사건번호": "2099다1", "법원명": "대법원",
                "사건명": "부당해고", "선고일자": "20990101", "판결유형": "판결",
                "판시사항": "[1] 부당해고 구제", "판결요지": "부당해고 구제에 관한 판단",
                "판례내용": "【주 문】 상고를 기각한다.\n【이 유】 부당해고 구제에 관한 판단이다.",
                "참조조문": "근로기준법 제23조"}


class FakeEmbedder:
    model_name = "fake"
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeStore:
    def __init__(self): self.upsert_calls = 0
    def upsert(self, chunks, vectors): self.upsert_calls += 1


class CaseEnrichmentTests(unittest.TestCase):
    def test_same_plan_is_cached_and_new_case_is_indexed_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "static.json").write_text("[]", encoding="utf-8")
            client, store = FakeClient(), FakeStore()
            enricher = IncrementalCaseEnricher(client, FakeEmbedder(), store,
                static_dataset=root / "static.json", dynamic_dataset=root / "dynamic.json",
                history_path=root / "history.json")
            plan = SearchPlan("[NAME_1] 해고", "부당해고 구제", ("부당해고",), False)

            first = enricher.enrich(plan, category=LegalCategory.LABOR)
            second = enricher.enrich(plan, category=LegalCategory.LABOR)

            self.assertEqual(first.new_case_count, 1)
            self.assertTrue(second.cache_hit)
            self.assertEqual(client.search_calls, 1)
            self.assertEqual(store.upsert_calls, 1)
            history = json.loads((root / "history.json").read_text(encoding="utf-8"))
            self.assertNotIn("[NAME_1]", json.dumps(history, ensure_ascii=False))

    def test_existing_case_number_is_not_fetched_or_reindexed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "static.json").write_text(json.dumps([{"case_number": "2099다1"}]), encoding="utf-8")
            client, store = FakeClient(), FakeStore()
            enricher = IncrementalCaseEnricher(client, FakeEmbedder(), store,
                static_dataset=root / "static.json", dynamic_dataset=root / "dynamic.json",
                history_path=root / "history.json")
            result = enricher.enrich(SearchPlan("질문", "부당해고", ("부당해고",), False),
                                     category=LegalCategory.LABOR)
            self.assertEqual(result.new_case_count, 0)
            self.assertEqual(client.fetch_calls, 0)
            self.assertEqual(store.upsert_calls, 0)

    def test_same_question_has_same_key_even_when_llm_terms_change(self):
        first = SearchPlan("같은 질문", "부당해고", ("부당해고",), True)
        second = SearchPlan("같은 질문", "해고 구제", ("해고", "구제명령"), True)
        self.assertEqual(
            IncrementalCaseEnricher.cache_key(first, LegalCategory.LABOR),
            IncrementalCaseEnricher.cache_key(second, LegalCategory.LABOR),
        )


if __name__ == "__main__":
    unittest.main()
