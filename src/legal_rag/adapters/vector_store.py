"""Chroma 기반 법령 청크 저장소."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.chunking import StatuteChunk
from legal_rag.rag.retrieval import VectorSearchHit


class ChromaStatuteVectorStore:
    def __init__(
        self,
        persist_directory: Path,
        *,
        collection_name: str = "safelaw_statutes",
        recreate: bool = False,
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("Chroma를 사용하려면 'pip install -e .'을 실행하세요.") from exc
        persist_directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_directory))
        if recreate:
            names = {
                getattr(item, "name", item)
                for item in self._client.list_collections()
            }
            if collection_name in names:
                self._client.delete_collection(collection_name)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: Sequence[StatuteChunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("청크와 벡터 개수가 다릅니다.")
        self._collection.upsert(
            ids=[item.chunk_id for item in chunks],
            documents=[item.content for item in chunks],
            embeddings=[list(vector) for vector in vectors],
            metadatas=[
                {
                    "category": item.category.value,
                    "law_id": item.law_id,
                    "law_name": item.law_name,
                    "article_no": item.article_no,
                    "article_title": item.article_title,
                    "chunk_index": item.chunk_index,
                    "chunk_count": item.chunk_count,
                    "effective_date": item.effective_date,
                    "source_url": item.source_url,
                    "issue_tags": ",".join(item.issue_tags),
                }
                for item in chunks
            ],
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def search(
        self,
        query_vector: Sequence[float],
        *,
        category: LegalCategory,
        top_k: int,
    ) -> list[VectorSearchHit]:
        result = self._collection.query(
            query_embeddings=[list(query_vector)],
            n_results=top_k,
            where={"category": category.value},
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            VectorSearchHit(
                chunk_id=chunk_id,
                document=document,
                metadata=metadata,
                distance=float(distance),
            )
            for chunk_id, document, metadata, distance in zip(
                ids, documents, metadatas, distances, strict=True
            )
        ]

