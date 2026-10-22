"""법령 검색, 근거 제한 생성, 인용 검증을 LangGraph retrieve/generate 노드로 연결한다."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

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
from legal_rag.rag.retrieval import RetrievalResult, RetrievedChunk


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
    generation_attempts: int = 0
    validation_failures: int = 0

    @property
    def is_answered(self) -> bool:
        return self.status is AnswerStatus.ANSWERED


class RagState(TypedDict, total=False):
    question: str
    category: LegalCategory
    top_k: int
    pinned_hits: tuple[RetrievedChunk, ...]
    retrieved_count: int
    evidence: tuple[LegalEvidence, ...]
    answer: GroundedAnswer


def evidence_from_retrieval(
    retrieval: RetrievalResult,
    pinned: Sequence[RetrievedChunk] = (),
) -> tuple[int, tuple[LegalEvidence, ...]]:
    """검색 결과를 [근거 N] 번호가 붙은 근거 목록으로 바꾼다. 고정 청크는 맨 앞에 한 번만 둔다."""

    pinned_ids = {hit.chunk_id for hit in pinned}
    statute_hits = (*pinned, *(hit for hit in retrieval.hits if hit.chunk_id not in pinned_ids))
    statute_evidence = build_statute_evidence(statute_hits)
    case_evidence = build_case_evidence(
        retrieval.case_hits,
        start_id=len(statute_evidence) + 1,
    )
    return len(statute_hits), (*statute_evidence, *case_evidence)


class StatuteRagPipeline:
    """마스킹된 질문만 받아 검증을 통과한 답변만 반환한다.

    retrieve 노드는 법령·판례 근거를 모으고, generate 노드는 그 근거만으로
    답변을 생성·검증한다. 근거가 없을 때의 차단도 generate가 맡아 그래프를
    두 노드의 직선 흐름으로 유지한다.
    """

    def __init__(
        self,
        retriever: StatuteRetriever,
        answer_llm: LanguageModel,
        *,
        max_generation_attempts: int = 3,
    ) -> None:
        if max_generation_attempts < 1:
            raise ValueError("max_generation_attempts는 1 이상이어야 합니다.")
        self._retriever = retriever
        self._answer_llm = answer_llm
        self._max_generation_attempts = max_generation_attempts
        self._graph = self._build_graph()

    @property
    def graph(self) -> Any:
        """컴파일된 LangGraph. 구조 출력과 노드 단위 검증에 사용한다."""

        return self._graph

    @property
    def retriever(self) -> StatuteRetriever:
        """검색 방식 비교처럼 같은 검색 계획을 재사용해야 할 때 사용한다."""

        return self._retriever

    def answer(
        self,
        sanitized_question: str,
        *,
        category: LegalCategory,
        top_k: int = 5,
        pinned_hits: Sequence[RetrievedChunk] = (),
    ) -> GroundedAnswer:
        """pinned_hits는 사용자가 선택한 항목(조문)으로, 검색 순위와 무관하게 근거 맨 앞에 둔다."""

        return self.answer_with_evidence(
            sanitized_question, category=category, top_k=top_k, pinned_hits=pinned_hits
        )[0]

    def answer_with_evidence(
        self,
        sanitized_question: str,
        *,
        category: LegalCategory,
        top_k: int = 5,
        pinned_hits: Sequence[RetrievedChunk] = (),
    ) -> tuple[GroundedAnswer, tuple[LegalEvidence, ...]]:
        """답변과 함께 retrieve 노드가 만든 근거 목록을 돌려줘 특화 기능이 같은 근거를 재사용하게 한다."""

        if not sanitized_question or not sanitized_question.strip():
            raise ValueError("마스킹된 질문이 필요합니다.")
        if top_k < 1:
            raise ValueError("top_k는 1 이상이어야 합니다.")

        state = self._graph.invoke(
            {
                "question": sanitized_question,
                "category": category,
                "top_k": top_k,
                "pinned_hits": tuple(pinned_hits),
            }
        )
        return state["answer"], tuple(state.get("evidence", ()))

    def _build_graph(self) -> Any:
        builder = StateGraph(RagState)
        builder.add_node("retrieve", self._retrieve_node)
        builder.add_node("generate", self._generate_node)
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", END)
        return builder.compile()

    def retrieve_evidence(
        self,
        sanitized_question: str,
        *,
        category: LegalCategory,
        top_k: int = 5,
        pinned_hits: Sequence[RetrievedChunk] = (),
    ) -> tuple[LegalEvidence, ...]:
        """retrieve 노드와 같은 방식으로 근거 목록만 만든다. Top-k별 근거 비교에 사용한다."""

        if top_k < 1:
            raise ValueError("top_k는 1 이상이어야 합니다.")
        return self._collect_evidence(sanitized_question, category, top_k, tuple(pinned_hits))[1]

    def _collect_evidence(
        self,
        question: str,
        category: LegalCategory,
        top_k: int,
        pinned: tuple[RetrievedChunk, ...],
    ) -> tuple[int, tuple[LegalEvidence, ...]]:
        retrieval = self._retriever.retrieve(question.strip(), category=category, top_k=top_k)
        return evidence_from_retrieval(retrieval, pinned)

    def _retrieve_node(self, state: RagState) -> RagState:
        retrieved_count, evidence = self._collect_evidence(
            state["question"],
            state["category"],
            state["top_k"],
            tuple(state.get("pinned_hits", ())),
        )
        return {"retrieved_count": retrieved_count, "evidence": evidence}

    def _generate_node(self, state: RagState) -> RagState:
        evidence = state["evidence"]
        if not evidence:
            return {"answer": self._blocked(AnswerStatus.NO_EVIDENCE, retrieved_count=state["retrieved_count"])}
        return {"answer": self._generate_answer(state["question"].strip(), state["category"], evidence)}

    def _generate_answer(
        self,
        sanitized_question: str,
        category: LegalCategory,
        evidence: tuple[LegalEvidence, ...],
    ) -> GroundedAnswer:
        messages = build_grounded_answer_messages(sanitized_question, category, evidence)
        validation_failures = 0
        retry_reason = ""
        for attempt in range(1, self._max_generation_attempts + 1):
            attempt_messages = list(messages)
            if attempt > 1:
                correction = (
                    "CONTEXT를 다시 사용하여 지정된 JSON 형식만 정확히 출력하라. "
                    "각 evidence_quotes.quote는 CONTEXT에서 공백을 제외하고도 연속으로 일치하는 "
                    "8자 이상의 원문을 그대로 복사하라. 근거가 부족하면 억지로 답하지 말라."
                )
                if attempt == self._max_generation_attempts:
                    correction += (
                        " 이번은 마지막 인용 교정이다. answerable=true라면 summary 한 개만 작성하고 "
                        "issues, favorable_factors, unfavorable_factors, additional_facts, next_steps는 "
                        "모두 빈 배열로 두어라. summary에는 가장 직접적인 근거 하나만 인용하라."
                    )
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "직전 응답은 폐기됐다. 실패 이유: " + retry_reason + " "
                            + correction
                        ),
                    }
                )
            try:
                raw_response = self._answer_llm.invoke(attempt_messages)
            except RuntimeError:
                return self._blocked(
                    AnswerStatus.GENERATION_FAILED,
                    retrieved_count=len(evidence),
                    generation_attempts=attempt,
                    validation_failures=validation_failures,
                )

            try:
                draft = parse_and_validate_draft(raw_response, evidence)
            except CitationValidationError as exc:
                validation_failures += 1
                retry_reason = str(exc)
                continue
            if not draft.answerable:
                if attempt < self._max_generation_attempts:
                    retry_reason = (
                        "answerable=false로 판단했다. 질문과 직접 관련된 CONTEXT가 실제로 있는지 "
                        "한 번 더 확인하되, 직접 근거가 없으면 다시 answerable=false로 답하라."
                    )
                    continue
                return self._blocked(
                    AnswerStatus.INSUFFICIENT_EVIDENCE,
                    retrieved_count=len(evidence),
                    generation_attempts=attempt,
                    validation_failures=validation_failures,
                )
            content = render_grounded_answer(draft, evidence)
            return GroundedAnswer(
                status=AnswerStatus.ANSWERED,
                content=content,
                sources=cited_evidence(draft, evidence),
                retrieved_count=len(evidence),
                generation_attempts=attempt,
                validation_failures=validation_failures,
            )

        return self._blocked(
            AnswerStatus.INVALID_CITATIONS,
            retrieved_count=len(evidence),
            generation_attempts=self._max_generation_attempts,
            validation_failures=validation_failures,
        )

    @staticmethod
    def _blocked(status: AnswerStatus, *, retrieved_count: int,
                 generation_attempts: int = 0, validation_failures: int = 0) -> GroundedAnswer:
        return GroundedAnswer(
            status=status,
            content=SAFE_MESSAGES[status],
            retrieved_count=retrieved_count,
            generation_attempts=generation_attempts,
            validation_failures=validation_failures,
        )

