import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient
from legal_rag.domain.models import LegalCategory, StatuteDocument
from legal_rag.rag.chunking import chunk_statute
from legal_rag.rag.indexing import index_chunks


class FakeEmbedder:
    model_name = "fake-embedding"

    def __init__(self):
        self.batch_sizes = []

    def embed(self, texts):
        self.batch_sizes.append(len(texts))
        return [[float(len(text)), 1.0, 0.0] for text in texts]


class MemoryStore:
    def upsert(self, chunks, vectors):
        self.chunks = list(chunks)
        self.vectors = [list(item) for item in vectors]


class IndexingTests(unittest.TestCase):
    def setUp(self):
        document = StatuteDocument(
            law_id="law:article",
            category=LegalCategory.LABOR,
            law_name="근로기준법",
            article_no="제1조",
            article_title="목적",
            text="목적 조문",
            effective_date=date(2026, 1, 1),
            source_url="https://www.law.go.kr/법령/근로기준법/제1조",
        )
        self.chunks = chunk_statute(document)

    def test_batches_embeddings_and_upserts_vectors(self):
        embedder = FakeEmbedder()
        store = MemoryStore()

        result = index_chunks(self.chunks * 3, embedder, store, batch_size=2)

        self.assertEqual(embedder.batch_sizes, [2, 1])
        self.assertEqual(len(store.vectors), 3)
        self.assertEqual(result.vector_dimension, 3)
        self.assertEqual(result.embedding_model, "fake-embedding")

    def test_gms_response_is_sorted_and_secret_is_not_in_repr(self):
        captured = {}

        def transport(request, timeout):
            captured["authorization"] = request.get_header("Authorization")
            return json.dumps(
                {"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]}
            ).encode()

        client = GmsEmbeddingClient("secret-key", transport=transport)
        vectors = client.embed(["첫째", "둘째"])

        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(captured["authorization"], "Bearer secret-key")
        self.assertNotIn("secret-key", repr(client))


if __name__ == "__main__":
    unittest.main()
