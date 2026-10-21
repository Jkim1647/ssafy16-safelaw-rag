"""질의 시 부족한 공개 판례만 수집하고 증분 색인하는 캐시 계층."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from legal_rag.collectors.court_cases import CourtCaseApiError, CourtCaseOpenApiClient, normalize_case
from legal_rag.domain.models import CaseDocument, LegalCategory, PrecedentLevel
from legal_rag.rag.case_chunking import chunk_cases
from legal_rag.rag.indexing import EmbeddingProvider, index_chunks
from legal_rag.rag.retrieval import SearchPlan


class CaseChunkStore(Protocol):
    def upsert(self, chunks: Any, vectors: Any) -> None: ...


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    cache_key: str
    cache_hit: bool
    candidate_count: int
    new_case_count: int
    new_chunk_count: int
    case_numbers: tuple[str, ...]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _document_from_dict(item: dict[str, Any]) -> CaseDocument:
    from datetime import date
    return CaseDocument(**{
        **item,
        "category": LegalCategory(item["category"]),
        "decision_date": date.fromisoformat(item["decision_date"]),
        "precedent_level": PrecedentLevel(item.get("precedent_level", "other")),
        "issues": tuple(item.get("issues", [])),
        "related_articles": tuple(item.get("related_articles", [])),
        "cited_cases": tuple(item.get("cited_cases", [])),
    })


def _serialize(document: CaseDocument) -> dict[str, Any]:
    item = asdict(document)
    item["category"] = document.category.value
    item["decision_date"] = document.decision_date.isoformat()
    item["precedent_level"] = document.precedent_level.value
    for name in ("issues", "related_articles", "cited_cases"):
        item[name] = list(item[name])
    return item


class IncrementalCaseEnricher:
    """법률 검색어만 외부 API에 보내고, 동일 검색 계획은 로컬 캐시한다."""

    def __init__(self, client: CourtCaseOpenApiClient, embedder: EmbeddingProvider,
                 store: CaseChunkStore, *, static_dataset: Path, dynamic_dataset: Path,
                 history_path: Path, display_per_term: int = 5) -> None:
        self._client = client
        self._embedder = embedder
        self._store = store
        self._static_dataset = static_dataset
        self._dynamic_dataset = dynamic_dataset
        self._history_path = history_path
        self._display_per_term = display_per_term

    @staticmethod
    def cache_key(plan: SearchPlan, category: LegalCategory) -> str:
        # LLM이 같은 질문에서 조금 다른 용어를 만들더라도 API 재호출을 막는다.
        # 질문은 마스킹 이후 값조차 기록하지 않고 단방향 해시만 남긴다.
        canonical = re.sub(r"\s+", " ", plan.original_query).strip()
        return hashlib.sha256(f"v2|{category.value}|{canonical}".encode()).hexdigest()

    @staticmethod
    def _terms(plan: SearchPlan) -> tuple[str, ...]:
        terms: list[str] = []
        for value in plan.legal_terms:
            cleaned = re.sub(r"\s+", " ", value).strip()
            if len(cleaned) >= 2 and cleaned not in terms:
                terms.append(cleaned)
        return tuple(terms[:3])

    def enrich(self, plan: SearchPlan, *, category: LegalCategory) -> EnrichmentResult:
        terms = self._terms(plan)
        key = self.cache_key(plan, category)
        history = _read_json(self._history_path, {"schema_version": 1, "entries": {}})
        cached = history.get("entries", {}).get(key)
        if cached and cached.get("status") == "completed":
            return EnrichmentResult(key, True, cached.get("candidate_count", 0), 0, 0,
                                    tuple(cached.get("case_numbers", [])))

        static_items = _read_json(self._static_dataset, [])
        dynamic_items = _read_json(self._dynamic_dataset, [])
        existing_numbers = {str(item.get("case_number", "")) for item in static_items + dynamic_items}
        seen_ids: set[str] = set()
        candidates = []
        for term in terms:
            for result in self._client.search(term, display=self._display_per_term):
                if result.source_name and result.source_name != "대법원":
                    continue
                if result.case_id in seen_ids or result.case_number in existing_numbers:
                    continue
                seen_ids.add(result.case_id)
                candidates.append((term, result))

        new_documents: list[CaseDocument] = []
        normalized_terms = [re.sub(r"[^0-9A-Za-z가-힣]", "", term) for term in terms]
        for _term, result in candidates:
            try:
                document = normalize_case(self._client.fetch(result.case_id), category, result)
            except CourtCaseApiError:
                continue
            searchable = re.sub(
                r"[^0-9A-Za-z가-힣]", "",
                " ".join((*document.issues, document.reasoning, *document.related_articles)),
            )
            if normalized_terms and not any(term in searchable for term in normalized_terms):
                continue
            if document.case_number in existing_numbers:
                continue
            existing_numbers.add(document.case_number)
            new_documents.append(document)

        chunks = chunk_cases(new_documents) if new_documents else []
        if chunks:
            index_chunks(chunks, self._embedder, self._store)  # type: ignore[arg-type]
            dynamic_items.extend(_serialize(item) for item in new_documents)
            _write_json(self._dynamic_dataset, dynamic_items)

        numbers = tuple(item.case_number for item in new_documents)
        history.setdefault("entries", {})[key] = {
            "category": category.value,
            "legal_terms": list(terms),
            "status": "completed",
            "candidate_count": len(candidates),
            "new_case_count": len(new_documents),
            "new_chunk_count": len(chunks),
            "case_numbers": list(numbers),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(self._history_path, history)
        return EnrichmentResult(key, False, len(candidates), len(new_documents), len(chunks), numbers)
