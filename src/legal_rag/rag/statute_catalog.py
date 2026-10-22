"""법령 조문을 서비스 항목으로 다루는 카탈로그.

조문 청크 데이터셋을 조문 단위로 묶어 목록 선택, 조건 탐색 결과 표시,
선택 조문의 근거 고정에 사용한다. 청크 메타데이터는 Chroma 색인과 같은
형태로 만들어 근거 병합 로직을 그대로 재사용한다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.retrieval import RetrievedChunk


@dataclass(frozen=True, slots=True)
class StatuteItem:
    item_id: str
    category: LegalCategory
    law_name: str
    article_no: str
    article_title: str
    source_url: str
    effective_date: str
    chunks: tuple[RetrievedChunk, ...]

    @property
    def label(self) -> str:
        title = f" ({self.article_title})" if self.article_title else ""
        return f"{self.law_name} {self.article_no}{title}"

    @property
    def text(self) -> str:
        return "\n".join(chunk.document for chunk in self.chunks)

    def pinned_hits(self) -> tuple[RetrievedChunk, ...]:
        return self.chunks


def item_id_for(category: LegalCategory | str, law_id: str) -> str:
    return f"{LegalCategory(category).value}:{law_id}"


def _chunk_from_record(record: Mapping[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=str(record["chunk_id"]),
        document=str(record["content"]),
        metadata={
            "category": str(record["category"]),
            "law_id": str(record["law_id"]),
            "law_name": str(record["law_name"]),
            "article_no": str(record["article_no"]),
            "article_title": str(record.get("article_title", "")),
            "chunk_index": int(record.get("chunk_index", 0)),
            "chunk_count": int(record.get("chunk_count", 1)),
            "effective_date": str(record.get("effective_date", "")),
            "source_url": str(record["source_url"]),
            "issue_tags": ",".join(record.get("issue_tags", ())),
        },
        distance=0.0,
    )


class StatuteCatalog:
    def __init__(self, items: Iterable[StatuteItem]) -> None:
        self._items = {item.item_id: item for item in items}

    @classmethod
    def from_chunk_records(cls, records: Iterable[Mapping[str, Any]]) -> "StatuteCatalog":
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for record in records:
            grouped.setdefault(item_id_for(record["category"], str(record["law_id"])), []).append(record)

        items = []
        for item_id, item_records in grouped.items():
            ordered = sorted(item_records, key=lambda record: int(record.get("chunk_index", 0)))
            first = ordered[0]
            items.append(
                StatuteItem(
                    item_id=item_id,
                    category=LegalCategory(first["category"]),
                    law_name=str(first["law_name"]),
                    article_no=str(first["article_no"]),
                    article_title=str(first.get("article_title", "")),
                    source_url=str(first["source_url"]),
                    effective_date=str(first.get("effective_date", "")),
                    chunks=tuple(_chunk_from_record(record) for record in ordered),
                )
            )
        return cls(items)

    @classmethod
    def from_chunk_file(cls, path: Path) -> "StatuteCatalog":
        return cls.from_chunk_records(json.loads(path.read_text(encoding="utf-8")))

    def __len__(self) -> int:
        return len(self._items)

    def get(self, item_id: str) -> StatuteItem:
        return self._items[item_id]

    def find(self, item_id: str) -> StatuteItem | None:
        return self._items.get(item_id)

    def items(self, category: LegalCategory | None = None) -> tuple[StatuteItem, ...]:
        return tuple(
            item for item in self._items.values()
            if category is None or item.category is category
        )
