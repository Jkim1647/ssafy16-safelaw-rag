import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.mmr import mmr_select
from legal_rag.rag.retrieval import (
    ExpandedStatuteRetriever,
    LegalQueryExpander,
    RetrievedChunk,
    SearchPlan,
    VectorSearchHit,
)


def chunk(chunk_id, score):
    return RetrievedChunk(chunk_id=chunk_id, document=chunk_id, metadata={}, distance=0.0, score=score)


# A와 B는 거의 같은 내용, C는 다른 쟁점이다.
EMBEDDINGS = {"A": [1.0, 0.0], "B": [0.99, 0.05], "C": [0.0, 1.0]}


class MmrSelectTests(unittest.TestCase):
    def test_prefers_a_different_candidate_over_a_near_duplicate(self):
        candidates = [chunk("A", 1.0), chunk("B", 0.95), chunk("C", 0.8)]

        selected = mmr_select(candidates, EMBEDDINGS, 2, lambda_mult=0.5)

        self.assertEqual([item.chunk_id for item in selected], ["A", "C"])

    def test_lambda_one_keeps_relevance_order(self):
        candidates = [chunk("A", 1.0), chunk("B", 0.95), chunk("C", 0.8)]

        selected = mmr_select(candidates, EMBEDDINGS, 2, lambda_mult=1.0)

        self.assertEqual([item.chunk_id for item in selected], ["A", "B"])

    def test_handles_small_pools_and_missing_embeddings(self):
        self.assertEqual(mmr_select([], EMBEDDINGS, 3), ())
        selected = mmr_select([chunk("A", 1.0), chunk("X", 0.5)], EMBEDDINGS, 5)
        self.assertEqual([item.chunk_id for item in selected], ["A", "X"])

    def test_rejects_invalid_arguments(self):
        with self.assertRaises(ValueError):
            mmr_select([chunk("A", 1.0)], EMBEDDINGS, 0)
        with self.assertRaises(ValueError):
            mmr_select([chunk("A", 1.0)], EMBEDDINGS, 1, lambda_mult=1.5)


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeStore:
    def __init__(self):
        self.requested_top_k = []

    def search(self, query_vector, *, category, top_k):
        self.requested_top_k.append(top_k)
        return [
            VectorSearchHit(chunk_id=item, document=item, metadata={"category": category.value}, distance=rank / 10)
            for rank, item in enumerate(["A", "B", "C"], start=1)
        ]

    def embeddings(self, ids):
        return {item: EMBEDDINGS[item] for item in ids}


PLAN = SearchPlan("해고", "해고 통지", (), False)


class RetrieverSearchModeTests(unittest.TestCase):
    def retriever(self, store, **options):
        return ExpandedStatuteRetriever(FakeEmbedder(), store, LegalQueryExpander(), **options)

    def test_similarity_mode_keeps_ranked_order(self):
        result = self.retriever(FakeStore()).retrieve_with_plan(PLAN, category=LegalCategory.LABOR, top_k=2)

        self.assertEqual([hit.chunk_id for hit in result.hits], ["A", "B"])

    def test_mmr_mode_fetches_a_wider_pool_and_diversifies(self):
        store = FakeStore()
        retriever = self.retriever(store, search_mode="mmr", mmr_fetch_k=30, mmr_lambda=0.5)

        result = retriever.retrieve_with_plan(PLAN, category=LegalCategory.LABOR, top_k=2)

        self.assertEqual([hit.chunk_id for hit in result.hits], ["A", "C"])
        self.assertTrue(all(top_k >= 30 for top_k in store.requested_top_k))

    def test_rejects_unknown_search_mode(self):
        with self.assertRaises(ValueError):
            self.retriever(FakeStore(), search_mode="random")


if __name__ == "__main__":
    unittest.main()
