"""수집, 검색, LLM 계약."""

from __future__ import annotations

from typing import Protocol, Sequence, TypeVar

from legal_rag.domain.models import CaseDocument, LegalCategory, StatuteDocument

DocumentT = TypeVar("DocumentT", StatuteDocument, CaseDocument)


class StatuteSource(Protocol):
    def search(self, query: str, category: LegalCategory) -> Sequence[StatuteDocument]: ...


class CaseSource(Protocol):
    def search(self, query: str, category: LegalCategory) -> Sequence[CaseDocument]: ...


class Retriever(Protocol[DocumentT]):
    def retrieve(
        self,
        query: str,
        *,
        category: LegalCategory,
        top_k: int,
    ) -> Sequence[DocumentT]: ...


class LanguageModel(Protocol):
    def invoke(self, messages: Sequence[dict[str, str]]) -> str: ...

