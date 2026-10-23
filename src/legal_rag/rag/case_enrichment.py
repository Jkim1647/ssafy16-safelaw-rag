"""새 질문마다 아직 없는 공개 판례만 수집하고 증분 색인하는 캐시 계층."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from legal_rag.collectors.court_cases import (
    CaseSearchResult,
    CourtCaseApiError,
    CourtCaseOpenApiClient,
    normalize_case,
)
from legal_rag.domain.models import CaseDocument, LegalCategory, PrecedentLevel
from legal_rag.rag.case_chunking import chunk_cases
from legal_rag.rag.case_selection import CaseSelectionError
from legal_rag.rag.indexing import EmbeddingProvider, index_chunks
from legal_rag.rag.retrieval import SearchPlan


class CaseChunkStore(Protocol):
    def upsert(self, chunks: Any, vectors: Any) -> None: ...


class CaseSelector(Protocol):
    def select(self, plan: SearchPlan, category: LegalCategory,
               candidates: Sequence[CaseSearchResult]) -> list[tuple[int, str]]: ...


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    """판례 목록 후보 하나가 색인됐는지, 왜 빠졌는지를 기록한다.

    decision: indexed(색인), rejected(선별 프롬프트 탈락), filtered(본문 쟁점어 불일치),
    duplicate(이미 보유), fetch_failed(본문 조회 실패)
    """

    case_number: str
    case_name: str
    court: str
    decision_date: str
    term: str
    decision: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class EnrichmentResult:
    cache_key: str
    cache_hit: bool
    candidate_count: int
    new_case_count: int
    new_chunk_count: int
    case_numbers: tuple[str, ...]
    selection_mode: str = "disabled"
    decisions: tuple[CandidateDecision, ...] = ()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


# 수집 이력과 동적 판례 파일은 읽고-고치고-쓰는 순서라, 같은 프로세스의 동시 요청
# (FastAPI 스레드, 여러 Streamlit 세션)이 서로의 기록을 덮지 않도록 이 구간만 잠근다.
_STATE_LOCK = threading.Lock()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 요청마다 다른 임시 파일에 쓴 뒤 교체해 임시 파일 이름이 겹치지 않게 한다.
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


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
                 history_path: Path, display_per_term: int = 5,
                 selector: CaseSelector | None = None,
                 chunk_max_chars: int = 1400, chunk_overlap_chars: int = 180) -> None:
        self._client = client
        self._embedder = embedder
        self._store = store
        self._static_dataset = static_dataset
        self._dynamic_dataset = dynamic_dataset
        self._history_path = history_path
        self._display_per_term = display_per_term
        self._selector = selector
        self._chunk_max_chars = chunk_max_chars
        self._chunk_overlap_chars = chunk_overlap_chars

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
            return EnrichmentResult(
                key, True, cached.get("candidate_count", 0), 0, 0,
                tuple(cached.get("case_numbers", [])),
                selection_mode=cached.get("selection_mode", "disabled"),
                decisions=tuple(CandidateDecision(**item) for item in cached.get("candidates", [])),
            )

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

        # 선별 프롬프트로 본문을 받을 후보를 먼저 정한다. 선별이 실패하면 기존처럼
        # 모든 후보의 본문을 받아 쟁점어 필터로만 거른다.
        selection_mode = "disabled"
        reasons: dict[int, str] = {}
        if self._selector is not None and candidates:
            try:
                reasons = dict(self._selector.select(plan, category, [result for _, result in candidates]))
                selection_mode = "llm"
            except CaseSelectionError:
                selection_mode = "keyword_fallback"
        fetch_all = selection_mode != "llm"

        new_documents: list[CaseDocument] = []
        decisions: list[CandidateDecision] = []
        normalized_terms = [re.sub(r"[^0-9A-Za-z가-힣]", "", term) for term in terms]
        for index, (term, result) in enumerate(candidates):
            decision = self._candidate_decision(
                term, result, category, existing_numbers, normalized_terms,
                selected=fetch_all or index in reasons, new_documents=new_documents,
            )
            decisions.append(CandidateDecision(
                case_number=result.case_number,
                case_name=result.case_name,
                court=result.court,
                decision_date=result.decision_date.isoformat(),
                term=term,
                decision=decision,
                reason=reasons.get(index, ""),
            ))

        chunks = chunk_cases(
            new_documents, max_chars=self._chunk_max_chars, overlap_chars=self._chunk_overlap_chars,
        ) if new_documents else []
        if chunks:
            index_chunks(chunks, self._embedder, self._store)  # type: ignore[arg-type]

        numbers = tuple(item.case_number for item in new_documents)
        entry = {
            "category": category.value,
            "legal_terms": list(terms),
            "status": "completed",
            "candidate_count": len(candidates),
            "new_case_count": len(new_documents),
            "new_chunk_count": len(chunks),
            "case_numbers": list(numbers),
            "selection_mode": selection_mode,
            # 선별 이유는 마스킹된 질문 맥락을 담을 수 있어 이력 파일에는 남기지 않는다.
            "candidates": [{**asdict(item), "reason": ""} for item in decisions],
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        # API 호출 동안 다른 요청이 파일을 바꿨을 수 있으므로 잠근 뒤 최신 내용을 다시 읽어 합친다.
        with _STATE_LOCK:
            if new_documents:
                latest_items = _read_json(self._dynamic_dataset, [])
                known = {str(item.get("case_number", "")) for item in latest_items}
                latest_items.extend(_serialize(item) for item in new_documents if item.case_number not in known)
                _write_json(self._dynamic_dataset, latest_items)
            latest_history = _read_json(self._history_path, {"schema_version": 1, "entries": {}})
            latest_history.setdefault("entries", {})[key] = entry
            _write_json(self._history_path, latest_history)
        return EnrichmentResult(key, False, len(candidates), len(new_documents), len(chunks), numbers,
                                selection_mode=selection_mode, decisions=tuple(decisions))

    def _candidate_decision(self, term: str, result: CaseSearchResult, category: LegalCategory,
                            existing_numbers: set[str], normalized_terms: list[str], *,
                            selected: bool, new_documents: list[CaseDocument]) -> str:
        if not selected:
            return "rejected"
        try:
            document = normalize_case(self._client.fetch(result.case_id), category, result)
        except CourtCaseApiError:
            return "fetch_failed"
        searchable = re.sub(
            r"[^0-9A-Za-z가-힣]", "",
            " ".join((*document.issues, document.reasoning, *document.related_articles)),
        )
        if normalized_terms and not any(term in searchable for term in normalized_terms):
            return "filtered"
        if document.case_number in existing_numbers:
            return "duplicate"
        existing_numbers.add(document.case_number)
        new_documents.append(document)
        return "indexed"
