import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_llm import GmsChatClient
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.retrieval import (
    ExpandedStatuteRetriever,
    LegalQueryExpander,
    VectorSearchHit,
)


class FakeLlm:
    def invoke(self, messages):
        return """```json
        {"rewritten_query":"해고 서면 통지 효력","legal_terms":["해고", "서면통지"]}
        ```"""


class FakeEmbedder:
    model_name = "fake"

    def embed(self, texts):
        return [[float(index)] for index, _ in enumerate(texts)]


class FakeStore:
    def search(self, query_vector, *, category, top_k):
        query_index = int(query_vector[0])
        if query_index == 0:
            order = ["wrong", "other", "target"]
        else:
            order = ["target", "other", "wrong"]
        return [
            VectorSearchHit(
                chunk_id=item,
                document=item,
                metadata={"article_no": item, "category": category.value},
                distance=rank / 10,
            )
            for rank, item in enumerate(order, start=1)
        ]


class QueryExpansionTests(unittest.TestCase):
    def test_rules_translate_everyday_dismissal_language(self):
        plan = LegalQueryExpander().expand(
            "회사에서 카카오톡으로 내일부터 나오지 말라고 했어요",
            LegalCategory.LABOR,
        )

        self.assertIn("해고", plan.legal_terms)
        self.assertIn("서면통지", plan.legal_terms)
        self.assertFalse(plan.used_llm)

    def test_llm_json_is_combined_with_rule_terms(self):
        plan = LegalQueryExpander(FakeLlm()).expand(
            "카톡으로 해고 통보를 받았습니다",
            LegalCategory.LABOR,
        )

        self.assertTrue(plan.used_llm)
        self.assertIn("서면통지", plan.rewritten_query)
        self.assertEqual(len(plan.legal_terms), len(set(plan.legal_terms)))

    def test_multi_query_fusion_promotes_expanded_match(self):
        retriever = ExpandedStatuteRetriever(
            FakeEmbedder(),
            FakeStore(),
            LegalQueryExpander(FakeLlm()),
        )

        result = retriever.retrieve(
            "카톡으로 내일부터 나오지 말라고 했어요",
            category=LegalCategory.LABOR,
            top_k=2,
        )

        self.assertEqual(result.hits[0].chunk_id, "target")
        self.assertGreater(len(result.hits[0].matched_queries), 1)

    def test_gms_chat_response_and_repr_do_not_leak_key(self):
        def transport(request, timeout):
            return json.dumps(
                {"choices": [{"message": {"content": '{"legal_terms":["해고"]}'}}]}
            ).encode()

        client = GmsChatClient("secret-key", transport=transport)

        self.assertIn("해고", client.invoke([{"role": "user", "content": "질문"}]))
        self.assertNotIn("secret-key", repr(client))


if __name__ == "__main__":
    unittest.main()
