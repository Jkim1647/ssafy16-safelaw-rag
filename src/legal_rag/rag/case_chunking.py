"""판례의 의미 단위를 보존하는 섹션 기반 청킹."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from legal_rag.domain.models import CaseDocument, LegalCategory, PrecedentLevel
from legal_rag.rag.chunking import CATEGORY_LABELS, _atomic_blocks, _pack_blocks


@dataclass(frozen=True, slots=True)
class CaseChunk:
    chunk_id: str
    category: LegalCategory
    case_id: str
    case_number: str
    court: str
    decision_date: str
    section: str
    section_index: int
    content: str
    embedding_text: str
    source_url: str
    related_articles: tuple[str, ...] = field(default_factory=tuple)
    case_name: str = ""
    decision_type: str = ""
    precedent_level: PrecedentLevel = PrecedentLevel.OTHER


SECTION_LABELS = {
    "issues": "법적 쟁점",
    "reasoning": "법원의 판단",
    "result": "주문·결과",
    "facts": "사실관계·판례 원문",
}


def chunk_case(document: CaseDocument, *, max_chars: int = 1400,
               overlap_chars: int = 180) -> list[CaseChunk]:
    if max_chars < 200:
        raise ValueError("max_chars는 200 이상이어야 합니다.")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars는 0 이상 max_chars 미만이어야 합니다.")

    sections = (
        ("issues", "\n".join(document.issues)),
        ("reasoning", document.reasoning),
        ("result", document.result),
        ("facts", document.facts),
    )
    chunks: list[CaseChunk] = []
    for section, text in sections:
        if not text.strip():
            continue
        contents = _pack_blocks(_atomic_blocks(text, max_chars, overlap_chars), max_chars, overlap_chars)
        for index, content in enumerate(contents):
            related = ", ".join(document.related_articles) or "없음"
            embedding_text = (
                f"도메인: {CATEGORY_LABELS[document.category]}\n"
                f"판례: {document.court} {document.case_number}\n"
                f"사건명: {document.case_name or '미상'}\n"
                f"판례 등급: {document.precedent_level.value}\n"
                f"판결 유형: {document.decision_type or '미상'}\n"
                f"섹션: {SECTION_LABELS[section]}\n"
                f"관련 법령: {related}\n"
                f"내용: {content}"
            )
            chunks.append(CaseChunk(
                chunk_id=f"case:{document.category.value}:{document.case_id}:{section}:{index:03d}",
                category=document.category,
                case_id=document.case_id,
                case_number=document.case_number,
                court=document.court,
                decision_date=document.decision_date.isoformat(),
                section=section,
                section_index=index,
                content=content,
                embedding_text=embedding_text,
                source_url=document.source_url,
                related_articles=document.related_articles,
                case_name=document.case_name,
                decision_type=document.decision_type,
                precedent_level=document.precedent_level,
            ))
    return chunks


def chunk_cases(documents: Iterable[CaseDocument], *, max_chars: int = 1400,
                overlap_chars: int = 180) -> list[CaseChunk]:
    chunks: list[CaseChunk] = []
    seen: set[str] = set()
    for document in documents:
        for chunk in chunk_case(document, max_chars=max_chars, overlap_chars=overlap_chars):
            if chunk.chunk_id in seen:
                raise ValueError(f"중복 판례 청크 ID: {chunk.chunk_id}")
            seen.add(chunk.chunk_id)
            chunks.append(chunk)
    return chunks
