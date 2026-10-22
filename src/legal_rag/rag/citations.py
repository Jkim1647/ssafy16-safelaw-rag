"""검색 근거와 LLM 구조화 답변의 인용을 검증한다."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from legal_rag.rag.retrieval import RetrievedChunk


ANSWER_SECTIONS = (
    "issues",
    "favorable_factors",
    "unfavorable_factors",
    "additional_facts",
    "next_steps",
)


class CitationValidationError(ValueError):
    """답변이 제공된 검색 근거에 묶여 있지 않을 때 발생한다."""


@dataclass(frozen=True, slots=True)
class StatuteEvidence:
    citation_id: int
    chunk_id: str
    law_name: str
    article_no: str
    article_title: str
    text: str
    source_url: str

    @property
    def label(self) -> str:
        title = f" ({self.article_title})" if self.article_title else ""
        return f"{self.law_name} {self.article_no}{title}"


@dataclass(frozen=True, slots=True)
class CaseEvidence:
    citation_id: int
    chunk_id: str
    case_id: str
    case_number: str
    court: str
    decision_date: str
    sections: tuple[str, ...]
    text: str
    source_url: str
    case_name: str = ""
    decision_type: str = ""
    precedent_level: str = "other"
    case_type: str = ""
    cited_cases: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        badge = "[전원합의체] " if self.precedent_level == "grand_bench" else ""
        name = f" {self.case_name}" if self.case_name else ""
        return f"{badge}{self.court} {self.decision_date} 선고 {self.case_number}{name}"


LegalEvidence = StatuteEvidence | CaseEvidence


@dataclass(frozen=True, slots=True)
class EvidenceQuote:
    citation_id: int
    quote: str


@dataclass(frozen=True, slots=True)
class GroundedClaim:
    text: str
    citation_ids: tuple[int, ...]
    evidence_quotes: tuple[EvidenceQuote, ...]


@dataclass(frozen=True, slots=True)
class GroundedDraft:
    answerable: bool
    summary: GroundedClaim | None = None
    issues: tuple[GroundedClaim, ...] = ()
    favorable_factors: tuple[GroundedClaim, ...] = ()
    unfavorable_factors: tuple[GroundedClaim, ...] = ()
    additional_facts: tuple[GroundedClaim, ...] = ()
    next_steps: tuple[GroundedClaim, ...] = ()

    @property
    def claims(self) -> tuple[GroundedClaim, ...]:
        values: list[GroundedClaim] = []
        if self.summary is not None:
            values.append(self.summary)
        for section in ANSWER_SECTIONS:
            values.extend(getattr(self, section))
        return tuple(values)


def _is_official_law_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "law.go.kr" or host.endswith(".law.go.kr"))


def build_statute_evidence(hits: Sequence[RetrievedChunk]) -> tuple[StatuteEvidence, ...]:
    """검색 청크를 공식 URL이 있는 조문 단위 근거로 병합한다."""

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for hit in hits:
        law_name = str(hit.metadata.get("law_name", "")).strip()
        article_no = str(hit.metadata.get("article_no", "")).strip()
        article_title = str(hit.metadata.get("article_title", "")).strip()
        source_url = str(hit.metadata.get("source_url", "")).strip()
        document = hit.document.strip()
        if not (law_name and article_no and document and _is_official_law_url(source_url)):
            continue
        key = law_name, article_no, source_url
        if key not in grouped:
            grouped[key] = {
                "chunk_id": hit.chunk_id,
                "article_title": article_title,
                "documents": [],
            }
        if document not in grouped[key]["documents"]:
            grouped[key]["documents"].append(document)

    evidence: list[StatuteEvidence] = []
    for citation_id, ((law_name, article_no, source_url), value) in enumerate(grouped.items(), start=1):
        evidence.append(
            StatuteEvidence(
                citation_id=citation_id,
                chunk_id=value["chunk_id"],
                law_name=law_name,
                article_no=article_no,
                article_title=value["article_title"],
                text="\n".join(value["documents"]),
                source_url=source_url,
            )
        )
    return tuple(evidence)


def build_case_evidence(
    hits: Sequence[RetrievedChunk], *, start_id: int = 1
) -> tuple[CaseEvidence, ...]:
    """같은 사건의 검색된 섹션 청크를 하나의 판례 근거로 병합한다."""

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for hit in hits:
        case_id = str(hit.metadata.get("case_id", "")).strip()
        source_url = str(hit.metadata.get("source_url", "")).strip()
        document = hit.document.strip()
        if not (case_id and document and _is_official_law_url(source_url)):
            continue
        key = case_id, source_url
        if key not in grouped:
            grouped[key] = {
                "chunk_id": hit.chunk_id,
                "case_number": str(hit.metadata.get("case_number", "")).strip(),
                "court": str(hit.metadata.get("court", "")).strip(),
                "decision_date": str(hit.metadata.get("decision_date", "")).strip(),
                "case_name": str(hit.metadata.get("case_name", "")).strip(),
                "decision_type": str(hit.metadata.get("decision_type", "")).strip(),
                "precedent_level": str(hit.metadata.get("precedent_level", "other")).strip(),
                "case_type": str(hit.metadata.get("case_type", "")).strip(),
                "cited_cases": tuple(
                    item.strip()
                    for item in str(hit.metadata.get("cited_cases", "")).split("|")
                    if item.strip()
                ),
                "sections": [],
                "documents": [],
            }
        section = str(hit.metadata.get("section", "")).strip()
        if section and section not in grouped[key]["sections"]:
            grouped[key]["sections"].append(section)
        if document not in grouped[key]["documents"]:
            grouped[key]["documents"].append(document)

    evidence: list[CaseEvidence] = []
    for offset, ((case_id, source_url), value) in enumerate(grouped.items()):
        if not (value["case_number"] and value["court"] and value["decision_date"]):
            continue
        evidence.append(CaseEvidence(
            citation_id=start_id + offset,
            chunk_id=value["chunk_id"],
            case_id=case_id,
            case_number=value["case_number"],
            court=value["court"],
            decision_date=value["decision_date"],
            sections=tuple(value["sections"]),
            text="\n".join(value["documents"]),
            source_url=source_url,
            case_name=value["case_name"],
            decision_type=value["decision_type"],
            precedent_level=value["precedent_level"],
            case_type=value["case_type"],
            cited_cases=value["cited_cases"],
        ))
    return tuple(evidence)


def extract_json_object(raw_response: str) -> dict[str, Any]:
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise CitationValidationError("답변 생성 결과가 비어 있습니다.")
    match = re.search(r"\{.*\}", raw_response, re.DOTALL)
    if not match:
        raise CitationValidationError("답변에서 JSON 객체를 찾을 수 없습니다.")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise CitationValidationError("답변 JSON 형식이 올바르지 않습니다.") from exc
    if not isinstance(payload, dict):
        raise CitationValidationError("답변은 JSON 객체여야 합니다.")
    return payload


def parse_grounded_claim(value: Any, evidence_by_id: dict[int, LegalEvidence]) -> GroundedClaim:
    if not isinstance(value, dict):
        raise CitationValidationError("주장은 text와 citations를 가진 객체여야 합니다.")
    text = value.get("text")
    citations = value.get("citations")
    raw_quotes = value.get("evidence_quotes")
    if not isinstance(text, str) or not text.strip():
        raise CitationValidationError("근거가 필요한 주장에 본문이 없습니다.")
    if re.search(r"https?://", text, re.IGNORECASE):
        raise CitationValidationError("생성 답변 본문에 검증되지 않은 URL이 포함되어 있습니다.")
    if not isinstance(citations, list) or not citations:
        raise CitationValidationError("모든 주장에는 하나 이상의 근거 번호가 필요합니다.")

    citation_ids: list[int] = []
    for citation_id in citations:
        if isinstance(citation_id, bool) or not isinstance(citation_id, int):
            raise CitationValidationError("근거 번호는 정수여야 합니다.")
        if citation_id not in evidence_by_id:
            raise CitationValidationError(f"존재하지 않는 근거 번호입니다: {citation_id}")
        if citation_id not in citation_ids:
            citation_ids.append(citation_id)

    if not isinstance(raw_quotes, list) or not raw_quotes:
        raise CitationValidationError("모든 주장에는 법령 원문의 근거 문구가 필요합니다.")
    evidence_quotes: list[EvidenceQuote] = []
    quoted_citation_ids: set[int] = set()
    for raw_quote in raw_quotes:
        if not isinstance(raw_quote, dict):
            raise CitationValidationError("근거 문구 형식이 올바르지 않습니다.")
        citation_id = raw_quote.get("citation_id")
        quote = raw_quote.get("quote")
        if isinstance(citation_id, bool) or not isinstance(citation_id, int):
            raise CitationValidationError("근거 문구의 citation_id는 정수여야 합니다.")
        if citation_id not in citation_ids:
            raise CitationValidationError("근거 문구 번호가 주장의 근거 번호와 일치하지 않습니다.")
        if not isinstance(quote, str) or len(quote.strip()) < 8:
            raise CitationValidationError("근거 문구가 너무 짧거나 비어 있습니다.")
        normalized_quote = re.sub(r"\s+", "", quote)
        normalized_source = re.sub(r"\s+", "", evidence_by_id[citation_id].text)
        if normalized_quote not in normalized_source:
            raise CitationValidationError("근거 문구가 검색된 법령 원문에 존재하지 않습니다.")
        evidence_quotes.append(EvidenceQuote(citation_id=citation_id, quote=quote.strip()))
        quoted_citation_ids.add(citation_id)
    if quoted_citation_ids != set(citation_ids):
        raise CitationValidationError("인용한 모든 근거에 대응하는 법령 원문 문구가 필요합니다.")

    mentioned_articles = set(re.findall(r"제\s*\d+조(?:의\s*\d+)?", text))
    cited_articles = {
        re.sub(r"\s+", "", evidence_by_id[citation_id].article_no)
        for citation_id in citation_ids
        if isinstance(evidence_by_id[citation_id], StatuteEvidence)
    }
    normalized_mentions = {re.sub(r"\s+", "", item) for item in mentioned_articles}
    if not normalized_mentions.issubset(cited_articles):
        raise CitationValidationError("본문에서 언급한 조문과 연결된 근거 번호가 일치하지 않습니다.")

    return GroundedClaim(
        text=text.strip(),
        citation_ids=tuple(citation_ids),
        evidence_quotes=tuple(evidence_quotes),
    )


def parse_and_validate_draft(
    raw_response: str,
    evidence: Sequence[LegalEvidence],
) -> GroundedDraft:
    """LLM JSON을 파싱하고 모든 주장에 유효한 검색 근거가 있는지 확인한다."""

    payload = extract_json_object(raw_response)
    if payload.get("answerable") is False:
        return GroundedDraft(answerable=False)
    if payload.get("answerable") is not True:
        raise CitationValidationError("answerable은 true 또는 false여야 합니다.")

    evidence_by_id = {item.citation_id: item for item in evidence}
    if not evidence_by_id:
        raise CitationValidationError("검증할 검색 근거가 없습니다.")
    summary = parse_grounded_claim(payload.get("summary"), evidence_by_id)
    sections: dict[str, tuple[GroundedClaim, ...]] = {}
    for section in ANSWER_SECTIONS:
        raw_items = payload.get(section, [])
        if not isinstance(raw_items, list):
            raise CitationValidationError(f"{section}은 배열이어야 합니다.")
        sections[section] = tuple(parse_grounded_claim(item, evidence_by_id) for item in raw_items)

    draft = GroundedDraft(answerable=True, summary=summary, **sections)
    if not draft.claims:
        raise CitationValidationError("검증할 주장이 없습니다.")
    return draft


def cited_evidence(
    draft: GroundedDraft,
    evidence: Sequence[LegalEvidence],
) -> tuple[LegalEvidence, ...]:
    used = {citation_id for claim in draft.claims for citation_id in claim.citation_ids}
    return tuple(item for item in evidence if item.citation_id in used)


def _citation_label(citation_ids: Iterable[int]) -> str:
    return " ".join(f"[근거 {citation_id}]" for citation_id in citation_ids)


def render_grounded_answer(draft: GroundedDraft, evidence: Sequence[LegalEvidence]) -> str:
    if not draft.answerable or draft.summary is None:
        raise CitationValidationError("답변 불가 초안은 렌더링할 수 없습니다.")

    lines = [
        "## 상황에 대한 법령·판례 안내",
        "",
        f"{draft.summary.text} {_citation_label(draft.summary.citation_ids)}",
    ]
    headings = {
        "issues": "핵심 법적 쟁점",
        "favorable_factors": "유리하게 검토할 요소",
        "unfavorable_factors": "불리하거나 주의할 요소",
        "additional_facts": "추가로 확인할 사실",
        "next_steps": "다음 행동",
    }
    for section, heading in headings.items():
        claims = getattr(draft, section)
        if not claims:
            continue
        lines.extend(("", f"### {heading}", ""))
        lines.extend(
            f"- {claim.text} {_citation_label(claim.citation_ids)}"
            for claim in claims
        )

    lines.extend(("", "### 확인된 근거", ""))
    for item in cited_evidence(draft, evidence):
        lines.append(f"- [근거 {item.citation_id}] [{item.label}]({item.source_url})")
    lines.extend(
        (
            "",
            "> 이 답변은 검색된 법령과 공개 판례를 설명하는 참고 정보이며 법률 자문이나 승소 가능성 예측이 아닙니다.",
        )
    )
    if any(isinstance(item, CaseEvidence) for item in cited_evidence(draft, evidence)):
        lines.extend(
            (
                "",
                "> 판례 선고 이후 관련 법령이 개정되거나 법리가 변경·제한되었을 수 있습니다. 선고일과 현재 법령, 후속 판례를 함께 확인해야 합니다.",
            )
        )
    return "\n".join(lines)

