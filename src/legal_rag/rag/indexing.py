"""청크 임베딩과 벡터 저장소 색인 오케스트레이션."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from legal_rag.rag.chunking import StatuteChunk


class EmbeddingProvider(Protocol):
    model_name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class ChunkVectorStore(Protocol):
    def upsert(self, chunks: Sequence[StatuteChunk], vectors: Sequence[Sequence[float]]) -> None: ...


@dataclass(frozen=True, slots=True)
class IndexResult:
    chunk_count: int
    vector_dimension: int
    embedding_model: str


def index_chunks(
    chunks: Sequence[StatuteChunk],
    embedder: EmbeddingProvider,
    store: ChunkVectorStore,
    *,
    batch_size: int = 64,
) -> IndexResult:
    if not chunks:
        raise ValueError("색인할 청크가 없습니다.")
    if batch_size < 1:
        raise ValueError("batch_size는 1 이상이어야 합니다.")

    all_vectors: list[list[float]] = []
    dimension: int | None = None
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = embedder.embed([item.embedding_text for item in batch])
        if len(vectors) != len(batch):
            raise ValueError("임베딩 응답 개수가 요청 텍스트 개수와 다릅니다.")
        for vector in vectors:
            if not vector:
                raise ValueError("빈 임베딩 벡터가 반환되었습니다.")
            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise ValueError("임베딩 벡터 차원이 일정하지 않습니다.")
        all_vectors.extend(vectors)

    store.upsert(chunks, all_vectors)
    return IndexResult(len(chunks), dimension or 0, embedder.model_name)

