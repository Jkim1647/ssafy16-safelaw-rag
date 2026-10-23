"""법률 검색어 확장과 다중 질의 순위 결합."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.indexing import EmbeddingProvider
from legal_rag.rag.mmr import mmr_select

logger = logging.getLogger(__name__)


CATEGORY_LABELS = {
    LegalCategory.LABOR: "근로계약·부당해고",
    LegalCategory.HOUSING_LEASE: "전세·임대차 보증금",
    LegalCategory.INHERITANCE: "상속",
}

PRECEDENT_AUTHORITY_BONUS = {
    "grand_bench": 0.0015,
    "supreme_court": 0.0008,
    "appellate": 0.0003,
}

GENERIC_CASE_TERMS = {
    "법률", "법령", "판례", "사례", "소송", "청구", "임금", "임금지급", "체불",
    "해고", "해고통보", "보증금", "전세", "임대차", "임대차계약", "임대차보증금",
    "보증금반환", "보증금회수", "상속", "상속재산", "부동산",
}


@dataclass(frozen=True, slots=True)
class SearchPlan:
    original_query: str
    rewritten_query: str
    legal_terms: tuple[str, ...]
    used_llm: bool

    def variants(self) -> list[tuple[str, float, str]]:
        candidates = [
            (self.original_query, 0.7, "primary"),
            (self.rewritten_query, 1.3, "primary"),
            *((term, 1.0, "term") for term in self.legal_terms),
        ]
        result: list[tuple[str, float, str]] = []
        seen: set[str] = set()
        for query, weight, kind in candidates:
            normalized = query.strip()
            if normalized and normalized not in seen:
                result.append((normalized, weight, kind))
                seen.add(normalized)
        return result


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    chunk_id: str
    document: str
    metadata: dict[str, Any]
    distance: float


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    document: str
    metadata: dict[str, Any]
    distance: float
    score: float = 0.0
    matched_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    plan: SearchPlan
    hits: tuple[RetrievedChunk, ...]
    case_hits: tuple[RetrievedChunk, ...] = ()


class VectorSearcher(Protocol):
    def search(
        self,
        query_vector: Sequence[float],
        *,
        category: LegalCategory,
        top_k: int,
    ) -> list[VectorSearchHit]: ...


SEARCH_MODES = ("similarity", "mmr")


class LanguageModel(Protocol):
    def invoke(self, messages: Sequence[dict[str, str]]) -> str: ...


def _unique_terms(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = re.sub(r"\s+", " ", str(value)).strip()
        if term and len(term) <= 40 and term not in seen:
            result.append(term)
            seen.add(term)
    return tuple(result[:8])


def _rule_terms(query: str, category: LegalCategory) -> tuple[str, ...]:
    terms: list[str] = []
    if category is LegalCategory.LABOR:
        dismissal = bool(re.search(r"해고|잘렸|잘랐|나오지\s*말|그만두|퇴사하라|계약\s*종료", query))
        written = bool(re.search(r"카카오톡|카톡|문자|메신저|말로|구두|전화", query))
        if dismissal:
            terms.extend(("해고", "해고 통보"))
        if dismissal and re.search(r"특별한\s*이유|이유도\s*설명|마음에\s*안|정당한\s*이유", query):
            terms.extend(("정당한 이유", "해고 등의 제한"))
        if dismissal and written:
            terms.extend(("서면통지", "해고사유", "해고시기", "해고 효력"))
        if re.search(r"월급|급여|임금|수당|돈을?\s*못\s*받", query):
            terms.extend(("임금", "임금 지급", "체불"))
        if re.search(r"계약직|기간제|단시간|알바", query):
            terms.extend(("기간제근로자", "단시간근로자"))
        if re.search(r"계약서|근로조건|월급.*근무시간|근무시간.*월급", query):
            terms.extend(("근로조건의 명시", "근로계약서 교부"))
        if re.search(r"퇴사|퇴직", query) and re.search(r"정산|마지막\s*월급|금품|못\s*받", query):
            terms.extend(("금품 청산", "퇴직 후 지급기한"))
    elif category is LegalCategory.HOUSING_LEASE:
        if re.search(r"보증금|전세금|집주인.*돈|돈.*돌려", query):
            terms.extend(("임대차보증금", "보증금 반환", "보증금 회수"))
        if re.search(r"경매|공매|채권자", query) and re.search(r"먼저|우선|배당|보증금|전세금", query):
            terms.extend(("보증금의 회수", "우선변제권"))
        if re.search(r"이사|전입|등기|못\s*받", query):
            terms.extend(("대항력", "우선변제권", "임차권등기명령"))
        if re.search(r"이사|점유.*잃|퇴거", query) and re.search(r"임차권등기|등기명령", query):
            terms.extend(("점유 상실", "임대차 종료 후 임차권등기"))
        if re.search(r"갱신|연장|더\s*살", query):
            terms.extend(("계약갱신요구권", "묵시적 갱신"))
        if re.search(r"소액", query) and re.search(r"보증금|임차", query):
            terms.extend(("보증금 중 일정액의 보호", "소액보증금 최우선변제"))
        if re.search(r"임대차.*등기|등기.*협조|세입자.*등기", query):
            terms.extend(("임대차의 등기", "임대인의 등기 협력"))
        if re.search(r"보일러|수선|수리.*거부|고장", query):
            terms.extend(("임대인의 의무", "목적물 사용수익 상태 유지", "수선의무"))
        if re.search(r"수리비|필요비|유익비|비용.*돌려", query):
            terms.extend(("임차인의 상환청구권", "필요비 상환"))
        if re.search(r"보험|보증공사|보증기관", query):
            terms.extend(("주택도시보증공사", "임차보증금 반환채권"))
        if re.search(r"지연손해금|집.*돌려주|주택.*인도|부동산.*인도", query):
            terms.extend(("동시이행", "임차목적물 인도", "보증채무"))
        if re.search(r"계속|존속|보증금.*받을 때까지", query) and re.search(r"보험|임대차", query):
            terms.extend(("임대차관계 존속", "임대차기간 중", "전세자금대출용권리보험"))
    elif category is LegalCategory.INHERITANCE:
        if re.search(r"빚|채무|대출", query):
            terms.extend(("상속채무", "상속포기", "한정승인"))
        if re.search(r"포기|받지\s*않", query):
            terms.extend(("상속포기", "상속의 승인과 포기", "신고기간"))
        if re.search(r"유언|유산|재산", query):
            terms.extend(("상속재산", "유언", "유류분"))
        if re.search(r"유류분", query) or (
            re.search(r"전\s*재산|모든\s*재산|재산을?\s*전부", query)
            and re.search(r"줬|주었|증여|넘겼|남겼|유증", query)
        ):
            # 누가 유류분을 청구할 수 있는지는 제1112조(유류분의 권리자와 유류분)가 정한다.
            terms.extend(("유류분의 권리자와 유류분", "유류분권리자", "유류분 반환청구"))
        if re.search(r"생전|미리", query) and re.search(r"증여|재산|돈|큰돈|받", query):
            terms.extend(("특별수익", "특별수익자의 상속분", "상속분 산정"))
        if re.search(r"누가\s*먼저|순서|순위", query):
            terms.extend(("상속의 순위", "법정상속순위"))
        if re.search(r"재산.*빚|빚.*이어받|모두\s*이어받|권리.*의무", query):
            terms.extend(("상속과 포괄적 권리의무의 승계", "포괄승계"))
        if re.search(r"한정승인", query) and re.search(r"효과|범위", query):
            terms.extend(("한정승인의 효과", "상속재산 범위의 채무 변제"))
    return _unique_terms(terms)


class LegalQueryExpander:
    """마스킹된 질문만 받아 검색용 표현을 만든다."""

    def __init__(self, llm: LanguageModel | None = None) -> None:
        self._llm = llm

    def expand(self, sanitized_query: str, category: LegalCategory) -> SearchPlan:
        query = re.sub(r"\s+", " ", sanitized_query).strip()
        if not query:
            raise ValueError("검색 질문이 필요합니다.")
        rule_terms = _rule_terms(query, category)
        llm_terms: tuple[str, ...] = ()
        rewritten = query
        used_llm = False

        if self._llm is not None:
            try:
                payload = self._expand_with_llm(query, category)
                llm_terms = _unique_terms(payload.get("legal_terms", []))
                candidate = str(payload.get("rewritten_query", "")).strip()
                if candidate:
                    rewritten = candidate
                used_llm = True
            except (ValueError, TypeError, RuntimeError, json.JSONDecodeError):
                used_llm = False

        terms = _unique_terms((*rule_terms, *llm_terms))
        if terms:
            rewritten = " ".join((rewritten, *terms))
        return SearchPlan(query, rewritten, terms, used_llm)

    def _expand_with_llm(self, query: str, category: LegalCategory) -> dict[str, Any]:
        response = self._llm.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "당신은 대한민국 생활법률 검색어 변환기다. 법률상 결론이나 승소 가능성을 "
                        "판단하지 말고 검색에 필요한 법률 용어만 추출한다. 사용자가 명시하지 않은 "
                        "사실을 만들지 않는다. 반드시 JSON 객체 하나만 출력한다. 형식: "
                        '{"rewritten_query":"법령 검색용 한 문장","legal_terms":["용어1","용어2"]}'
                    ),
                },
                {
                    "role": "user",
                    "content": f"도메인: {CATEGORY_LABELS[category]}\n마스킹된 질문: {query}",
                },
            ]
        )
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise ValueError("LLM 응답에 JSON 객체가 없습니다.")
        payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("LLM 검색어 응답이 객체가 아닙니다.")
        return payload


class ExpandedStatuteRetriever:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        store: VectorSearcher,
        expander: LegalQueryExpander,
        *,
        candidate_pool_factor: int = 3,
        deduplicate_metadata_key: str | None = None,
        search_mode: str = "similarity",
        mmr_fetch_k: int = 30,
        mmr_lambda: float = 0.5,
    ) -> None:
        if candidate_pool_factor < 1:
            raise ValueError("candidate_pool_factor는 1 이상이어야 합니다.")
        if search_mode not in SEARCH_MODES:
            raise ValueError(f"search_mode는 {', '.join(SEARCH_MODES)} 중 하나여야 합니다.")
        if mmr_fetch_k < 1 or not 0.0 <= mmr_lambda <= 1.0:
            raise ValueError("mmr_fetch_k는 1 이상, mmr_lambda는 0~1이어야 합니다.")
        self._embedder = embedder
        self._store = store
        self._expander = expander
        self._candidate_pool_factor = candidate_pool_factor
        self._deduplicate_metadata_key = deduplicate_metadata_key
        self._search_mode = search_mode
        self._mmr_fetch_k = mmr_fetch_k
        self._mmr_lambda = mmr_lambda

    @property
    def search_mode(self) -> str:
        return self._search_mode

    def plan(self, sanitized_query: str, category: LegalCategory) -> SearchPlan:
        return self._expander.expand(sanitized_query, category)

    def retrieve(
        self,
        sanitized_query: str,
        *,
        category: LegalCategory,
        top_k: int = 5,
    ) -> RetrievalResult:
        if top_k < 1:
            raise ValueError("top_k는 1 이상이어야 합니다.")
        plan = self._expander.expand(sanitized_query, category)
        return self.retrieve_with_plan(plan, category=category, top_k=top_k)

    def retrieve_with_plan(
        self,
        plan: SearchPlan,
        *,
        category: LegalCategory,
        top_k: int = 5,
    ) -> RetrievalResult:
        """이미 만든 검색 계획을 재사용해 LLM 검색어 변환 중복 호출을 막는다."""
        if top_k < 1:
            raise ValueError("top_k는 1 이상이어야 합니다.")
        variants = plan.variants()
        vectors = self._embedder.embed([query for query, _, _ in variants])
        if len(vectors) != len(variants):
            raise ValueError("검색 질의와 임베딩 개수가 다릅니다.")

        fused: dict[str, RetrievedChunk] = {}
        best_term_scores: dict[str, float] = {}
        # MMR은 최종 개수보다 넉넉한 후보 풀에서 다양성을 고르므로 검색 후보도 그만큼 늘린다.
        final_count = max(top_k, self._mmr_fetch_k) if self._search_mode == "mmr" else top_k
        candidate_count = max(final_count * self._candidate_pool_factor, 10)
        for (query, weight, kind), vector in zip(variants, vectors, strict=True):
            hits = self._store.search(vector, category=category, top_k=candidate_count)
            for rank, hit in enumerate(hits, start=1):
                item = fused.get(hit.chunk_id)
                if item is None:
                    item = RetrievedChunk(
                        chunk_id=hit.chunk_id,
                        document=hit.document,
                        metadata=hit.metadata,
                        distance=hit.distance,
                    )
                    fused[hit.chunk_id] = item
                variant_score = weight / (60 + rank)
                if kind == "primary":
                    item.score += variant_score
                else:
                    best_term_scores[hit.chunk_id] = max(
                        best_term_scores.get(hit.chunk_id, 0.0),
                        variant_score,
                    )
                item.distance = min(item.distance, hit.distance)
                item.matched_queries.append(query)

        case_specific_matches: dict[str, int] = {}
        normalized_specific_terms = {
            normalized
            for term in plan.legal_terms
            if (normalized := re.sub(r"[^0-9A-Za-z가-힣]", "", term))
            and len(normalized) >= 4
            and normalized not in GENERIC_CASE_TERMS
        }
        for item in fused.values():
            item.score += best_term_scores.get(item.chunk_id, 0.0)
            title = str(item.metadata.get("article_title", ""))
            normalized_title = re.sub(r"[^0-9A-Za-z가-힣]", "", title)
            title_bonus = 0.0
            document_bonus = 0.0
            for term in plan.legal_terms:
                normalized_term = re.sub(r"[^0-9A-Za-z가-힣]", "", term)
                if not normalized_term:
                    continue
                if normalized_term == normalized_title:
                    title_bonus = max(title_bonus, 0.05)
                elif len(normalized_term) >= 4 and (
                    normalized_term in normalized_title or normalized_title in normalized_term
                ):
                    title_bonus = max(title_bonus, 0.02)
                if term in item.document:
                    document_bonus = max(document_bonus, 0.002)
            item.score += title_bonus + document_bonus
            if item.metadata.get("document_type") == "court_case":
                # 임베딩/RRF가 비슷한 판례 사이에서는 사건명과 본문에 실제로
                # 나타난 구체 법률어를 이용해 재정렬한다. 짧고 일반적인 단어
                # 하나가 순위를 독점하지 않도록 용어별·전체 보너스를 제한한다.
                case_name = re.sub(
                    r"[^0-9A-Za-z가-힣]", "", str(item.metadata.get("case_name", ""))
                )
                searchable = re.sub(
                    r"[^0-9A-Za-z가-힣]", "",
                    " ".join((
                        str(item.metadata.get("case_name", "")),
                        str(item.metadata.get("related_articles", "")),
                        item.document,
                    )),
                )
                matched_weight = 0.0
                name_bonus = 0.0
                meaningful_terms = 0
                for term in plan.legal_terms:
                    normalized_term = re.sub(r"[^0-9A-Za-z가-힣]", "", term)
                    if len(normalized_term) < 2:
                        continue
                    meaningful_terms += 1
                    specificity = min(len(normalized_term), 8) / 8
                    if normalized_term in searchable:
                        matched_weight += 0.001 + (0.0015 * specificity)
                    if normalized_term in case_name:
                        name_bonus = max(name_bonus, 0.006 + (0.006 * specificity))
                coverage = matched_weight / meaningful_terms if meaningful_terms else 0.0
                case_specific_matches[item.chunk_id] = sum(
                    term in searchable for term in normalized_specific_terms
                )
                item.score += min(matched_weight, 0.012) + min(name_bonus, 0.012)
                item.score += min(coverage * 2, 0.004)
                item.score += PRECEDENT_AUTHORITY_BONUS.get(
                    str(item.metadata.get("precedent_level", "")), 0.0
                )

        ranked = sorted(
            fused.values(),
            key=lambda item: (-item.score, item.distance, item.chunk_id),
        )
        if self._deduplicate_metadata_key:
            deduplicated: list[RetrievedChunk] = []
            seen_values: set[str] = set()
            for item in ranked:
                value = str(item.metadata.get(self._deduplicate_metadata_key, ""))
                key = value or item.chunk_id
                if key in seen_values:
                    continue
                seen_values.add(key)
                deduplicated.append(item)
                if len(deduplicated) == final_count:
                    break
            ranked = deduplicated
        if normalized_specific_terms and any(case_specific_matches.get(item.chunk_id, 0) for item in ranked):
            # 구체 쟁점어가 실제로 확인되는 후보가 있으면 일반어만 맞은 주변 판례는
            # 생성 근거에서 제외한다. 전부 탈락할 때는 기존 의미 검색으로 폴백한다.
            ranked = [
                item for item in ranked
                if case_specific_matches.get(item.chunk_id, 0) > 0
            ]
        if self._search_mode == "mmr":
            pool = ranked[:final_count]
            embeddings = self._store.embeddings([item.chunk_id for item in pool])  # type: ignore[attr-defined]
            return RetrievalResult(
                plan=plan,
                hits=mmr_select(pool, embeddings, top_k, lambda_mult=self._mmr_lambda),
            )
        return RetrievalResult(plan=plan, hits=tuple(ranked[:top_k]))


class CombinedLegalRetriever:
    """법령과 판례를 독립 검색하고 원 점수를 직접 비교하지 않는다."""

    def __init__(self, statute_retriever: ExpandedStatuteRetriever,
                 case_retriever: ExpandedStatuteRetriever,
                 case_enricher: object | None = None) -> None:
        self._statute_retriever = statute_retriever
        self._case_retriever = case_retriever
        self._case_enricher = case_enricher

    def plan(self, sanitized_query: str, category: LegalCategory) -> SearchPlan:
        return self._statute_retriever.plan(sanitized_query, category)

    def retrieve(self, sanitized_query: str, *, category: LegalCategory,
                 top_k: int = 5) -> RetrievalResult:
        plan = self.plan(sanitized_query, category)
        if self._case_enricher is not None:
            try:
                self._case_enricher.enrich(plan, category=category)  # type: ignore[attr-defined]
            except Exception as exc:
                # 실시간 보강 실패가 기존 정적 판례 검색까지 중단시키지 않게 한다.
                # 예외 메시지에는 API 주소의 OC 값이나 질문이 섞일 수 있어 종류만 남긴다.
                logger.warning("판례 실시간 보강에 실패해 기존 판례 색인으로 검색합니다: %s", type(exc).__name__)
        return self.retrieve_with_plan(plan, category=category, top_k=top_k)

    def retrieve_with_plan(self, plan: SearchPlan, *, category: LegalCategory,
                           top_k: int = 5) -> RetrievalResult:
        """판례 실시간 보강 없이 같은 검색 계획으로 법령·판례를 검색한다."""
        statutes = self._statute_retriever.retrieve_with_plan(plan, category=category, top_k=top_k)
        cases = self._case_retriever.retrieve_with_plan(
            plan, category=category, top_k=max(top_k * 3, 10)
        )
        unique_cases: list[RetrievedChunk] = []
        seen_case_numbers: set[str] = set()
        for hit in cases.hits:
            case_number = str(hit.metadata.get("case_number", ""))
            key = case_number or hit.chunk_id
            if key in seen_case_numbers:
                continue
            seen_case_numbers.add(key)
            unique_cases.append(hit)
            if len(unique_cases) == top_k:
                break
        return RetrievalResult(
            plan=statutes.plan,
            hits=statutes.hits,
            case_hits=tuple(unique_cases),
        )

