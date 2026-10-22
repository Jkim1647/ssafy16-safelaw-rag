"""Maximal Marginal Relevance로 근거 후보의 다양성을 확보한다.

이미 검색·재정렬된 후보 풀에서, 질문 관련성은 높으면서 앞서 고른 근거와는
내용이 겹치지 않는 후보를 차례로 고른다. 관련성은 재정렬 점수를 풀 안에서
0~1로 정규화해 쓰고, 근거 간 유사도는 색인에 저장된 임베딩의 코사인 유사도로 계산한다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from legal_rag.rag.retrieval import RetrievedChunk


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def mmr_select(
    candidates: Sequence[RetrievedChunk],
    embeddings: Mapping[str, Sequence[float]],
    k: int,
    *,
    lambda_mult: float = 0.5,
) -> tuple[RetrievedChunk, ...]:
    """lambda_mult가 1이면 관련성 순서 그대로, 0에 가까울수록 다양성을 우선한다."""

    if k < 1:
        raise ValueError("k는 1 이상이어야 합니다.")
    if not 0.0 <= lambda_mult <= 1.0:
        raise ValueError("lambda_mult는 0 이상 1 이하여야 합니다.")
    if not candidates:
        return ()

    scores = [item.score for item in candidates]
    low, high = min(scores), max(scores)
    relevance = {
        item.chunk_id: (item.score - low) / (high - low) if high > low else 1.0
        for item in candidates
    }
    remaining = list(candidates)
    selected: list[RetrievedChunk] = []
    while remaining and len(selected) < k:
        def marginal(item: RetrievedChunk) -> float:
            vector = embeddings.get(item.chunk_id)
            redundancy = max(
                (
                    _cosine(vector, embeddings[chosen.chunk_id])
                    for chosen in selected
                    if vector is not None and chosen.chunk_id in embeddings
                ),
                default=0.0,
            )
            return lambda_mult * relevance[item.chunk_id] - (1 - lambda_mult) * redundancy

        best = max(remaining, key=marginal)
        selected.append(best)
        remaining.remove(best)
    return tuple(selected)
