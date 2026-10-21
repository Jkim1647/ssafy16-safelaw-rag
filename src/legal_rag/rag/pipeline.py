"""법령 검색, 근거 제한 생성, 인용 검증을 연결한다."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.citations import (
    CitationValidationError,
    LegalEvidence,
    StatuteEvidence,
    build_case_evidence,
    build_statute_evidence,
    cited_evidence,
    parse_and_validate_draft,
    render_grounded_answer,
)
from legal_rag.rag.prompts import build_grounded_answer_messages
from legal_rag.rag.retrieval import RetrievalResult


class LanguageModel(Protocol):
    def invoke(self, messages: Sequence[dict[str, str]]) -> str: ...


class StatuteRetriever(Protocol):
    def retrieve(
        self,
        sanitized_query: str,
        *,
        category: LegalCategory,
        top_k: int = 5,
    ) -> RetrievalResult: ...


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    NO_EVIDENCE = "no_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INVALID_CITATIONS = "invalid_citations"
    GENERATION_FAILED = "generation_failed"


SAFE_MESSAGES = {
    AnswerStatus.NO_EVIDENCE: "관련 법령 근거를 찾지 못해 답변을 생성하지 않았습니다.",
    AnswerStatus.INSUFFICIENT_EVIDENCE: "검색된 법령만으로는 질문에 답하기 어려워 답변을 생성하지 않았습니다.",
    AnswerStatus.INVALID_CITATIONS: "생성된 답변의 근거를 검증할 수 없어 답변을 표시하지 않습니다.",
    AnswerStatus.GENERATION_FAILED: "답변 생성 중 오류가 발생해 검증되지 않은 답변을 표시하지 않습니다.",
}


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    status: AnswerStatus
    content: str
    sources: tuple[LegalEvidence, ...] = ()
    retrieved_count: int = 0

    @property
    def is_answered(self) -> bool:
        return self.status is AnswerStatus.ANSWERED


class StatuteRagPipeline:
    """마스킹된 질문만 받아 검증을 통과한 답변만 반환한다."""

    def __init__(
        self,
        retriever: StatuteRetriever,
        answer_llm: LanguageModel,
        *,
        max_generation_attempts: int = 2,
    ) -> None:
        if max_generation_attempts < 1:
            raise ValueError("max_generation_attempts는 1 이상이어야 합니다.")
        self._retriever = retriever
        self._answer_llm = answer_llm
        self._max_generation_attempts = max_generation_attempts

    def answer(
        self,
        sanitized_question: str,
        *,
        category: LegalCategory,
        top_k: int = 5,
    ) -> GroundedAnswer:
        if not sanitized_question or not sanitized_question.strip():
            raise ValueError("마스킹된 질문이 필요합니다.")
        if top_k < 1:
            raise ValueError("top_k는 1 이상이어야 합니다.")

        retrieval = self._retriever.retrieve(
            sanitized_question.strip(),
            category=category,
            top_k=top_k,
        )
        statute_evidence = build_statute_evidence(retrieval.hits)
        case_evidence = build_case_evidence(
            retrieval.case_hits,
            start_id=len(statute_evidence) + 1,
        )
        evidence: tuple[LegalEvidence, ...] = (*statute_evidence, *case_evidence)
        if not evidence:
            return self._blocked(AnswerStatus.NO_EVIDENCE, retrieved_count=len(retrieval.hits))

        messages = build_grounded_answer_messages(sanitized_question.strip(), category, evidence)
        for attempt in range(1, self._max_generation_attempts + 1):
            attempt_messages = list(messages)
            if attempt > 1:
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "직전 응답은 JSON 형식 또는 근거 검증을 통과하지 못해 폐기됐다. "
                            "CONTEXT를 다시 사용하여 지정된 JSON 형식만 정확히 출력하라."
                        ),
                    }
                )
            try:
                raw_response = self._answer_llm.invoke(attempt_messages)
            except RuntimeError:
                return self._blocked(
                    AnswerStatus.GENERATION_FAILED,
                    retrieved_count=len(evidence),
                )

            try:
                draft = parse_and_validate_draft(raw_response, evidence)
            except CitationValidationError:
                continue
            if not draft.answerable:
                return self._blocked(
                    AnswerStatus.INSUFFICIENT_EVIDENCE,
                    retrieved_count=len(evidence),
                )
            content = render_grounded_answer(draft, evidence)
            return GroundedAnswer(
                status=AnswerStatus.ANSWERED,
                content=content,
                sources=cited_evidence(draft, evidence),
                retrieved_count=len(evidence),
            )

        return self._blocked(
            AnswerStatus.INVALID_CITATIONS,
            retrieved_count=len(evidence),
        )

    @staticmethod
    def _blocked(status: AnswerStatus, *, retrieved_count: int) -> GroundedAnswer:
        return GroundedAnswer(
            status=status,
            content=SAFE_MESSAGES[status],
            retrieved_count=retrieved_count,
        )

