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
from legal_rag.rag.case_selection import CaseSelectionError
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


class TwoCaseClient:
    """1번은 쟁점과 무관한 사건, 2번은 부당해고 사건이다."""

    DETAILS = {
        "1": ("2099다1", "임대차보증금반환", "[1] 임대차 보증금 반환", "보증금 반환에 관한 판단"),
        "2": ("2099다2", "부당해고구제재심판정취소", "[1] 부당해고 구제", "부당해고 구제에 관한 판단"),
    }

    def __init__(self):
        self.fetched_ids = []

    def search(self, query, *, display=5):
        return [
            CaseSearchResult(case_id, number, name, "대법원", date(2099, 1, int(case_id)), "판결", "대법원")
            for case_id, (number, name, _, _) in self.DETAILS.items()
        ]

    def fetch(self, case_id):
        self.fetched_ids.append(case_id)
        number, name, issue, reasoning = self.DETAILS[case_id]
        return {"판례정보일련번호": case_id, "사건번호": number, "법원명": "대법원",
                "사건명": name, "선고일자": f"2099010{case_id}", "판결유형": "판결",
                "판시사항": issue, "판결요지": reasoning,
                "판례내용": f"【주 문】 상고를 기각한다.\n【이 유】 {reasoning}이다.",
                "참조조문": ""}


class FakeSelector:
    def __init__(self, picks=(), error=None):
        self.picks = list(picks)
        self.error = error
        self.received = None

    def select(self, plan, category, candidates):
        self.received = (plan, category, tuple(candidates))
        if self.error:
            raise self.error
        return self.picks


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

    def _enricher(self, root, client, store, selector):
        (root / "static.json").write_text("[]", encoding="utf-8")
        return IncrementalCaseEnricher(client, FakeEmbedder(), store,
            static_dataset=root / "static.json", dynamic_dataset=root / "dynamic.json",
            history_path=root / "history.json", selector=selector)

    def test_selector_decides_which_case_bodies_are_fetched(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            client, store = TwoCaseClient(), FakeStore()
            selector = FakeSelector([(1, "부당해고 구제 쟁점")])
            plan = SearchPlan("[NAME_1] 해고", "부당해고 구제", ("부당해고",), False)

            result = self._enricher(root, client, store, selector).enrich(plan, category=LegalCategory.LABOR)

            self.assertEqual(client.fetched_ids, ["2"])
            self.assertEqual(result.selection_mode, "llm")
            self.assertEqual(result.case_numbers, ("2099다2",))
            self.assertEqual(
                [(item.case_number, item.decision) for item in result.decisions],
                [("2099다1", "rejected"), ("2099다2", "indexed")],
            )
            self.assertEqual(result.decisions[1].reason, "부당해고 구제 쟁점")
            history = json.loads((root / "history.json").read_text(encoding="utf-8"))
            entry = next(iter(history["entries"].values()))
            self.assertEqual(entry["selection_mode"], "llm")
            self.assertEqual(
                [(item["case_number"], item["decision"]) for item in entry["candidates"]],
                [("2099다1", "rejected"), ("2099다2", "indexed")],
            )
            serialized = json.dumps(history, ensure_ascii=False)
            self.assertNotIn("[NAME_1]", serialized)
            self.assertNotIn("부당해고 구제 쟁점", serialized)

    def test_selector_failure_falls_back_to_keyword_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            client, store = TwoCaseClient(), FakeStore()
            selector = FakeSelector(error=CaseSelectionError("invalid"))

            result = self._enricher(root, client, store, selector).enrich(
                SearchPlan("질문", "부당해고", ("부당해고",), False), category=LegalCategory.LABOR
            )

            self.assertEqual(result.selection_mode, "keyword_fallback")
            self.assertEqual(sorted(client.fetched_ids), ["1", "2"])
            self.assertEqual(
                [(item.case_number, item.decision) for item in result.decisions],
                [("2099다1", "filtered"), ("2099다2", "indexed")],
            )

    def test_cache_hit_returns_recorded_decisions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            enricher = self._enricher(root, TwoCaseClient(), FakeStore(), FakeSelector([(1, "")]))
            plan = SearchPlan("질문", "부당해고", ("부당해고",), False)
            enricher.enrich(plan, category=LegalCategory.LABOR)

            cached = enricher.enrich(plan, category=LegalCategory.LABOR)

            self.assertTrue(cached.cache_hit)
            self.assertEqual(cached.selection_mode, "llm")
            self.assertEqual([item.decision for item in cached.decisions], ["rejected", "indexed"])

    def test_same_question_has_same_key_even_when_llm_terms_change(self):
        first = SearchPlan("같은 질문", "부당해고", ("부당해고",), True)
        second = SearchPlan("같은 질문", "해고 구제", ("해고", "구제명령"), True)
        self.assertEqual(
            IncrementalCaseEnricher.cache_key(first, LegalCategory.LABOR),
            IncrementalCaseEnricher.cache_key(second, LegalCategory.LABOR),
        )


if __name__ == "__main__":
    unittest.main()
