import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.citations import build_statute_evidence
from legal_rag.rag.condition_search import ConditionSearchError, StatuteConditionSearch
from legal_rag.rag.retrieval import RetrievalResult, SearchPlan
from legal_rag.rag.statute_catalog import StatuteCatalog


def chunk_record(article, title, content, *, index=0, count=1, category="labor", law_name="근로기준법"):
    law_id = f"001872:{article:04d}001"
    return {
        "chunk_id": f"{category}:{law_id}:{index:03d}",
        "category": category,
        "law_id": law_id,
        "law_name": law_name,
        "article_no": f"제{article}조",
        "article_title": title,
        "content": content,
        "chunk_index": index,
        "chunk_count": count,
        "effective_date": "2026-10-08",
        "source_url": f"https://www.law.go.kr/법령/{law_name}/제{article}조",
        "issue_tags": ["해고", "근로계약"],
    }


RECORDS = [
    chunk_record(26, "해고의 예고", "사용자는 근로자를 해고하려면 적어도 30일 전에 예고를 하여야 한다."),
    chunk_record(27, "해고사유 등의 서면통지", "사용자는 근로자를 해고하려면 해고사유와 해고시기를 서면으로 통지하여야 한다."),
    chunk_record(61, "연차 유급휴가의 사용 촉진", "첫 번째 청크 본문입니다.", index=0, count=2),
    chunk_record(61, "연차 유급휴가의 사용 촉진", "두 번째 청크 본문입니다.", index=1, count=2),
    chunk_record(3, "대항력 등", "임대차는 그 등기가 없는 경우에도 대항력이 있다.",
                 category="housing_lease", law_name="주택임대차보호법"),
]


class FakeRetriever:
    def __init__(self, catalog, item_ids):
        self.catalog = catalog
        self.item_ids = item_ids
        self.received = None

    def retrieve(self, sanitized_query, *, category, top_k=5):
        self.received = (sanitized_query, category, top_k)
        hits = [hit for item_id in self.item_ids for hit in self.catalog.get(item_id).pinned_hits()]
        return RetrievalResult(plan=SearchPlan(sanitized_query, sanitized_query, (), False), hits=tuple(hits))


class FakeLlm:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.response


class StatuteCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = StatuteCatalog.from_chunk_records(RECORDS)

    def test_groups_chunks_into_one_item_per_article(self):
        labor = self.catalog.items(LegalCategory.LABOR)

        self.assertEqual([item.article_no for item in labor], ["제26조", "제27조", "제61조"])
        article_61 = self.catalog.get("labor:001872:0061001")
        self.assertEqual(len(article_61.pinned_hits()), 2)
        self.assertIn("두 번째 청크", article_61.text)
        self.assertEqual(len(self.catalog.items(LegalCategory.HOUSING_LEASE)), 1)
        self.assertEqual(len(self.catalog), 4)

    def test_pinned_hits_become_official_statute_evidence(self):
        item = self.catalog.get("labor:001872:0027001")

        evidence = build_statute_evidence(item.pinned_hits())

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].article_no, "제27조")
        self.assertEqual(item.label, "근로기준법 제27조 (해고사유 등의 서면통지)")

    def test_loads_processed_chunk_file(self):
        catalog = StatuteCatalog.from_chunk_file(ROOT / "data" / "processed" / "statute_chunks.json")

        self.assertGreaterEqual(len(catalog), 100)
        self.assertTrue(all(catalog.items(category) for category in LegalCategory))

    def test_unknown_item_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.catalog.get("labor:missing")


class StatuteConditionSearchTests(unittest.TestCase):
    def setUp(self):
        self.catalog = StatuteCatalog.from_chunk_records(RECORDS)
        self.retriever = FakeRetriever(
            self.catalog,
            ["labor:001872:0027001", "labor:001872:0026001", "labor:001872:0061001"],
        )

    def test_returns_only_candidates_selected_by_llm(self):
        llm = FakeLlm(json.dumps({"selected": [{"id": "C1", "reason": "해고 서면통지를 다룬다"}]}, ensure_ascii=False))
        search = StatuteConditionSearch(self.retriever, llm, self.catalog, candidate_count=8)

        result = search.search("해고 통보 방식 관련 조문", category=LegalCategory.LABOR)

        self.assertEqual(self.retriever.received, ("해고 통보 방식 관련 조문", LegalCategory.LABOR, 8))
        self.assertEqual([item.article_no for item in result.candidates], ["제27조", "제26조", "제61조"])
        self.assertEqual([match.item.article_no for match in result.matches], ["제27조"])
        self.assertEqual(result.matches[0].reason, "해고 서면통지를 다룬다")
        self.assertIn("해고 통보 방식 관련 조문", llm.messages[-1]["content"])
        self.assertIn("C3", llm.messages[-1]["content"])

    def test_ignores_unknown_and_duplicate_ids(self):
        llm = FakeLlm('{"selected": [{"id": "C9"}, {"id": "C2", "reason": "예고"}, {"id": "C2"}]}')
        search = StatuteConditionSearch(self.retriever, llm, self.catalog)

        result = search.search("해고 예고", category=LegalCategory.LABOR)

        self.assertEqual([match.item.article_no for match in result.matches], ["제26조"])

    def test_empty_selection_is_a_valid_result(self):
        search = StatuteConditionSearch(self.retriever, FakeLlm('{"selected": []}'), self.catalog)

        result = search.search("상속 포기", category=LegalCategory.LABOR)

        self.assertEqual(result.matches, ())
        self.assertEqual(len(result.candidates), 3)

    def test_invalid_llm_output_raises_search_error(self):
        search = StatuteConditionSearch(self.retriever, FakeLlm("조문을 고를 수 없습니다"), self.catalog)

        with self.assertRaises(ConditionSearchError):
            search.search("해고", category=LegalCategory.LABOR)

    def test_llm_failure_raises_search_error(self):
        search = StatuteConditionSearch(self.retriever, FakeLlm(error=RuntimeError("down")), self.catalog)

        with self.assertRaises(ConditionSearchError):
            search.search("해고", category=LegalCategory.LABOR)

    def test_does_not_call_llm_without_candidates(self):
        llm = FakeLlm('{"selected": []}')
        search = StatuteConditionSearch(FakeRetriever(self.catalog, []), llm, self.catalog)

        result = search.search("해고", category=LegalCategory.LABOR)

        self.assertEqual(result.candidates, ())
        self.assertIsNone(llm.messages)

    def test_rejects_blank_condition(self):
        search = StatuteConditionSearch(self.retriever, FakeLlm('{"selected": []}'), self.catalog)

        with self.assertRaises(ValueError):
            search.search("  ", category=LegalCategory.LABOR)


if __name__ == "__main__":
    unittest.main()
