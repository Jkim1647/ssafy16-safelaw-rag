"""법령 조문 구조를 보존하는 결정적 청킹."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from legal_rag.domain.models import LegalCategory, StatuteDocument


CATEGORY_LABELS = {
    LegalCategory.LABOR: "근로계약·부당해고",
    LegalCategory.HOUSING_LEASE: "전세·임대차 보증금",
    LegalCategory.INHERITANCE: "상속",
}


@dataclass(frozen=True, slots=True)
class StatuteChunk:
    chunk_id: str
    category: LegalCategory
    law_id: str
    law_name: str
    article_no: str
    article_title: str
    content: str
    embedding_text: str
    chunk_index: int
    chunk_count: int
    effective_date: str
    source_url: str
    issue_tags: tuple[str, ...] = field(default_factory=tuple)


def _clean_block(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value).strip()


def _split_long_block(block: str, max_chars: int, overlap_chars: int) -> list[str]:
    """긴 항·호를 가능한 한 문장/공백 경계에서 나눈다."""
    parts: list[str] = []
    start = 0
    while start < len(block):
        hard_end = min(start + max_chars, len(block))
        end = hard_end
        if hard_end < len(block):
            search_from = start + max_chars // 2
            boundary = max(
                block.rfind(". ", search_from, hard_end),
                block.rfind("다. ", search_from, hard_end),
                block.rfind("\n", search_from, hard_end),
                block.rfind(" ", search_from, hard_end),
            )
            if boundary > start:
                end = boundary + 1
        part = block[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(block):
            break
        start = max(end - overlap_chars, start + 1)
    return parts


def _atomic_blocks(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    blocks: list[str] = []
    for line in text.splitlines():
        cleaned = _clean_block(line)
        if not cleaned:
            continue
        if len(cleaned) <= max_chars:
            blocks.append(cleaned)
        else:
            blocks.extend(_split_long_block(cleaned, max_chars, overlap_chars))
    return blocks


def _pack_blocks(blocks: list[str], max_chars: int, overlap_chars: int) -> list[str]:
    if not blocks:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for block in blocks:
        separator = 1 if current else 0
        if current and current_size + separator + len(block) > max_chars:
            chunks.append("\n".join(current))
            overlap: list[str] = []
            overlap_size = 0
            for previous in reversed(current):
                extra = len(previous) + (1 if overlap else 0)
                if overlap_size + extra > overlap_chars:
                    break
                overlap.insert(0, previous)
                overlap_size += extra
            while overlap and overlap_size + 1 + len(block) > max_chars:
                removed = overlap.pop(0)
                overlap_size -= len(removed) + (1 if overlap else 0)
            current = overlap
            current_size = overlap_size
        separator = 1 if current else 0
        current.append(block)
        current_size += separator + len(block)

    if current:
        chunks.append("\n".join(current))
    return chunks


def chunk_statute(
    document: StatuteDocument,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[StatuteChunk]:
    if max_chars < 200:
        raise ValueError("max_chars는 200 이상이어야 합니다.")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars는 0 이상 max_chars 미만이어야 합니다.")

    blocks = _atomic_blocks(document.text, max_chars, overlap_chars)
    contents = _pack_blocks(blocks, max_chars, overlap_chars)
    chunks: list[StatuteChunk] = []
    for index, content in enumerate(contents):
        tags = ", ".join(document.issue_tags) or "없음"
        embedding_text = (
            f"도메인: {CATEGORY_LABELS[document.category]}\n"
            f"법령: {document.law_name}\n"
            f"조문: {document.article_no} ({document.article_title})\n"
            f"관련 쟁점: {tags}\n"
            f"본문:\n{content}"
        )
        chunks.append(
            StatuteChunk(
                chunk_id=f"{document.category.value}:{document.law_id}:{index:03d}",
                category=document.category,
                law_id=document.law_id,
                law_name=document.law_name,
                article_no=document.article_no,
                article_title=document.article_title,
                content=content,
                embedding_text=embedding_text,
                chunk_index=index,
                chunk_count=len(contents),
                effective_date=document.effective_date.isoformat(),
                source_url=document.source_url,
                issue_tags=document.issue_tags,
            )
        )
    return chunks


def chunk_statutes(
    documents: Iterable[StatuteDocument],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[StatuteChunk]:
    chunks: list[StatuteChunk] = []
    seen_ids: set[str] = set()
    for document in documents:
        for chunk in chunk_statute(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        ):
            if chunk.chunk_id in seen_ids:
                raise ValueError(f"중복 청크 ID: {chunk.chunk_id}")
            seen_ids.add(chunk.chunk_id)
            chunks.append(chunk)
    return chunks

