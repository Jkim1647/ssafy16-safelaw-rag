"""SafeLaw Streamlit 사용자 인터페이스."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient
from legal_rag.adapters.gms_llm import GmsChatClient
from legal_rag.adapters.vector_store import ChromaCaseVectorStore, ChromaStatuteVectorStore
from legal_rag.config import Settings
from legal_rag.collectors.court_cases import CourtCaseOpenApiClient
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.pipeline import AnswerStatus, GroundedAnswer, StatuteRagPipeline
from legal_rag.rag.case_enrichment import IncrementalCaseEnricher
from legal_rag.rag.citations import CaseEvidence
from legal_rag.rag.retrieval import CombinedLegalRetriever, ExpandedStatuteRetriever, LegalQueryExpander
from legal_rag.security.redaction import PrivacyGuard


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDEX_PATH = PROJECT_ROOT / "data" / "indexes" / "statutes"
CASE_INDEX_PATH = PROJECT_ROOT / "data" / "indexes" / "cases"
STATIC_CASE_DATASET = PROJECT_ROOT / "data" / "processed" / "cases.json"
CASE_CACHE_PATH = PROJECT_ROOT / "data" / "cache"

CATEGORY_LABELS = {
    LegalCategory.LABOR: "근로계약·부당해고",
    LegalCategory.HOUSING_LEASE: "전세·임대차 보증금",
    LegalCategory.INHERITANCE: "상속",
}

CATEGORY_HELP = {
    LegalCategory.LABOR: "해고 통보, 임금, 근로계약서, 퇴직 정산",
    LegalCategory.HOUSING_LEASE: "전세보증금, 우선변제, 계약 갱신, 수선 의무",
    LegalCategory.INHERITANCE: "상속 순위, 상속포기, 한정승인, 유류분",
}

EXAMPLE_QUESTIONS = {
    LegalCategory.LABOR: (
        "5명 이상이 근무하는 회사에서 8개월째 일하고 있습니다. 어제 팀장이 카카오톡으로 "
        "'내일부터 나오지 말라'고 했고, 해고 사유와 날짜가 적힌 문서는 받지 못했습니다. "
        "이런 통보가 유효한지 알고 싶습니다.",
        "퇴사한 지 20일이 지났는데 마지막 월급과 연차수당을 받지 못했습니다. 회사는 다음 "
        "급여일에 주겠다고 합니다. 언제까지 지급해야 하나요?",
        "근로계약서를 받지 못했고 월급과 근무시간도 구두로만 들었습니다. 사업주가 계약서를 "
        "작성하거나 교부하지 않아도 되는지 궁금합니다.",
    ),
    LegalCategory.HOUSING_LEASE: (
        "전입신고와 확정일자를 마친 세입자입니다. 집이 경매로 넘어갔는데 보증금 8천만 원을 "
        "다른 채권자보다 먼저 받을 수 있는지 알고 싶습니다.",
        "계약이 끝나 이사해야 하지만 집주인이 새 세입자가 들어와야 보증금을 준다고 합니다. "
        "보증금을 받기 전에 이사할 경우 권리를 지키려면 어떤 조치를 해야 하나요?",
        "입주 중 보일러가 고장 나 수리를 요청했지만 집주인이 거부해 제가 비용을 냈습니다. "
        "이 수리비를 집주인에게 청구할 수 있나요?",
    ),
    LegalCategory.INHERITANCE: (
        "부모님이 돌아가신 뒤 예금보다 대출이 더 많다는 사실을 알았습니다. 사망 사실을 안 지 "
        "두 달 정도 됐는데 상속포기나 한정승인을 언제까지 해야 하나요?",
        "배우자와 자녀가 있는 사람이 유언 없이 사망했습니다. 부모와 형제자매도 있을 때 "
        "누가 먼저 상속받고 각자의 순위는 어떻게 되나요?",
        "상속재산 일부를 이미 사용한 뒤 채무를 발견했습니다. 이런 경우에도 상속포기나 "
        "한정승인을 할 수 있는지 궁금합니다.",
    ),
}


class UiConfigurationError(RuntimeError):
    """사용자가 해결할 수 있는 로컬 실행 환경 오류."""


@dataclass(frozen=True, slots=True)
class StatusPresentation:
    title: str
    icon: str
    level: str


STATUS_PRESENTATIONS = {
    AnswerStatus.ANSWERED: StatusPresentation("근거 검증 완료", "✅", "success"),
    AnswerStatus.NO_EVIDENCE: StatusPresentation("관련 법령 없음", "🔎", "warning"),
    AnswerStatus.INSUFFICIENT_EVIDENCE: StatusPresentation("근거 부족", "🛡️", "warning"),
    AnswerStatus.INVALID_CITATIONS: StatusPresentation("인용 검증 실패", "🛡️", "error"),
    AnswerStatus.GENERATION_FAILED: StatusPresentation("답변 생성 실패", "⚠️", "error"),
}


def parse_sensitive_terms(value: str) -> tuple[str, ...]:
    """쉼표·줄바꿈으로 입력한 추가 마스킹 단어를 중복 없이 정리한다."""

    result: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;\n]", value):
        term = raw.strip()
        if term and term not in seen:
            result.append(term)
            seen.add(term)
    return tuple(result[:20])


def runtime_readiness(settings: Settings, index_path: Path = INDEX_PATH) -> tuple[bool, str]:
    if not settings.has_gms_key:
        return False, ".env에 GMS_KEY를 설정해 주세요."
    if not index_path.exists():
        return False, "법령 색인이 없습니다. build_statute_index.py를 먼저 실행해 주세요."
    return True, "GMS와 법령 색인을 사용할 수 있습니다."


def build_pipeline(settings: Settings, index_path: Path = INDEX_PATH) -> StatuteRagPipeline:
    ready, message = runtime_readiness(settings, index_path)
    if not ready:
        raise UiConfigurationError(message)
    assert settings.gms_key is not None
    query_llm = GmsChatClient(
        settings.gms_key,
        model_name=settings.query_model,
        base_url=settings.gms_base_url,
    )
    answer_llm = GmsChatClient(
        settings.gms_key,
        model_name=settings.answer_model,
        base_url=settings.gms_base_url,
    )
    store = ChromaStatuteVectorStore(index_path)
    if store.count == 0:
        raise UiConfigurationError("법령 색인이 비어 있습니다. build_statute_index.py를 실행해 주세요.")
    embedder = GmsEmbeddingClient(
            settings.gms_key,
            model_name=settings.gms_embedding_model,
            base_url=settings.gms_base_url,
        )
    statute_retriever = ExpandedStatuteRetriever(
        embedder,
        store,
        LegalQueryExpander(query_llm),
    )
    if CASE_INDEX_PATH.exists():
        case_store = ChromaCaseVectorStore(CASE_INDEX_PATH)
        if case_store.count:
            case_retriever = ExpandedStatuteRetriever(
                embedder,
                case_store,
                LegalQueryExpander(query_llm),
                candidate_pool_factor=10,
                deduplicate_metadata_key="case_number",
            )
            enricher = None
            if settings.has_law_api_key and STATIC_CASE_DATASET.exists():
                assert settings.law_api_oc is not None
                enricher = IncrementalCaseEnricher(
                    CourtCaseOpenApiClient(settings.law_api_oc),
                    embedder,
                    case_store,
                    static_dataset=STATIC_CASE_DATASET,
                    dynamic_dataset=CASE_CACHE_PATH / "dynamic_cases.json",
                    history_path=CASE_CACHE_PATH / "case_collection_history.json",
                )
            return StatuteRagPipeline(
                CombinedLegalRetriever(statute_retriever, case_retriever, enricher),
                answer_llm,
            )
    return StatuteRagPipeline(statute_retriever, answer_llm)


def _inject_styles(st: Any) -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f7f8f5; }
        .block-container { max-width: 980px; padding-top: 2rem; padding-bottom: 4rem; }
        .safelaw-kicker { color: #316b52; font-size: .82rem; font-weight: 700;
            letter-spacing: .08em; text-transform: uppercase; }
        .safelaw-title { color: #17231d; font-size: 2.35rem; font-weight: 780;
            letter-spacing: -.035em; margin: .2rem 0 .5rem; }
        .safelaw-subtitle { color: #53645a; font-size: 1.02rem; margin-bottom: 1.5rem; }
        .privacy-box { background: #eef5f0; border: 1px solid #cfe0d5; border-radius: 14px;
            padding: 1rem 1.1rem; color: #294536; margin: .75rem 0 1.25rem; }
        [data-testid="stForm"] { background: white; border: 1px solid #dde4df;
            border-radius: 18px; padding: 1.35rem; box-shadow: 0 8px 28px rgba(40,65,50,.06); }
        [data-testid="stSidebar"] { background: #eef2ed; }
        div.stButton > button, div[data-testid="stFormSubmitButton"] > button {
            border-radius: 10px; font-weight: 700; }
        div[data-testid="stFormSubmitButton"] > button {
            background: #316b52 !important; border-color: #316b52 !important; color: white !important; }
        div[data-testid="stFormSubmitButton"] > button:hover {
            background: #285943 !important; border-color: #285943 !important; color: white !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar(st: Any, settings: Settings, ready: bool, readiness_message: str) -> None:
    with st.sidebar:
        st.subheader("SafeLaw")
        st.caption("개인정보 보호형 생활법률 검색")
        if ready:
            st.success("시스템 준비 완료", icon="✅")
        else:
            st.error(readiness_message, icon="⚠️")
        st.divider()
        st.markdown("**지원 도메인**")
        for category, label in CATEGORY_LABELS.items():
            st.markdown(f"- **{label}**  \n  {CATEGORY_HELP[category]}")
        st.divider()
        st.markdown("**개인정보 보호**")
        st.caption(
            "전화번호·주민등록번호·이메일·주소와 직접 지정한 단어는 "
            "외부 모델 호출 전에 로컬에서 마스킹합니다. 질문 원문은 파일이나 Vector DB에 저장하지 않습니다."
        )
        with st.expander("실행 정보"):
            st.code(
                f"환경: {settings.app_env}\n"
                f"검색어 변환 모델: {settings.query_model}\n"
                f"답변 생성 모델: {settings.answer_model}\n"
                f"임베딩 모델: {settings.gms_embedding_model}",
                language="text",
            )
            st.caption(
                "판례 자동 보강: "
                + ("활성화" if settings.has_law_api_key else "비활성화 (LAW_API_OC 미설정)")
            )


def _render_result(
    st: Any,
    answer: GroundedAnswer,
    *,
    original_text: str,
    sanitized_text: str,
    redaction_count: int,
) -> None:
    presentation = STATUS_PRESENTATIONS[answer.status]
    st.subheader("검토 결과")
    message = f"{presentation.icon} {presentation.title}"
    getattr(st, presentation.level)(message)
    st.caption(
        f"개인정보 마스킹 {redaction_count}건 · 검색 근거 {answer.retrieved_count}건 · "
        f"상태 코드 `{answer.status.value}`"
    )

    if redaction_count:
        st.markdown("#### 개인정보 마스킹 비교")
        original_column, sanitized_column = st.columns(2)
        with original_column:
            with st.container(border=True):
                st.markdown("**입력 원문**")
                st.caption("현재 브라우저·로컬 앱에서만 확인")
                st.write(original_text)
        with sanitized_column:
            with st.container(border=True):
                st.markdown("**외부 모델 전달문**")
                st.caption("검색·임베딩·LLM에 사용")
                st.write(sanitized_text)
        st.caption(
            "원문과 치환 매핑은 현재 요청을 처리하는 메모리에만 유지하며 "
            "파일·로그·Vector DB에 저장하지 않습니다."
        )

    if answer.is_answered:
        st.markdown(answer.content)
        if answer.sources:
            with st.expander("근거 링크만 모아보기"):
                statutes = [item for item in answer.sources if not isinstance(item, CaseEvidence)]
                cases = [item for item in answer.sources if isinstance(item, CaseEvidence)]
                if statutes:
                    st.markdown("**법령 근거**")
                for source in statutes:
                    st.link_button(
                        f"근거 {source.citation_id} · {source.label}",
                        source.source_url,
                        use_container_width=True,
                    )
                if cases:
                    st.markdown("**유사 판례**")
                for source in cases:
                    st.link_button(
                        f"근거 {source.citation_id} · {source.label}",
                        source.source_url,
                        use_container_width=True,
                    )
    else:
        st.warning(answer.content)
        st.caption("질문을 구체화하거나 다른 도메인을 선택한 뒤 다시 시도해 주세요.")


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("Streamlit을 사용하려면 'pip install -e .'을 실행하세요.") from exc

    st.set_page_config(
        page_title="SafeLaw | 근거 기반 생활법률 안내",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_styles(st)

    settings = Settings.from_environment()
    ready, readiness_message = runtime_readiness(settings)
    _render_sidebar(st, settings, ready, readiness_message)

    st.markdown('<div class="safelaw-kicker">Privacy-first legal RAG</div>', unsafe_allow_html=True)
    st.markdown('<div class="safelaw-title">상황을 적으면 관련 법령과 판례를 확인합니다</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="safelaw-subtitle">검색된 법령과 공개 판례 원문으로 검증할 수 있는 내용만 안내하고, 근거가 부족하면 답변하지 않습니다.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="privacy-box">🔒 입력한 개인정보는 외부 호출 전에 마스킹됩니다. '
        '정확한 이름·전화번호·상세 주소는 가능하면 입력하지 마세요.</div>',
        unsafe_allow_html=True,
    )

    category = st.selectbox(
        "상담 분야",
        options=[None, *list(LegalCategory)],
        index=0,
        format_func=lambda item: (
            "상담 받으실 분야를 선택해 주세요"
            if item is None
            else CATEGORY_LABELS[item]
        ),
        help="현재 법령 데이터가 구축된 세 분야 중 하나를 선택하세요.",
        key="legal_category_v3",
    )
    if category is not None:
        with st.expander("질문 예시 보기", expanded=True):
            for number, example in enumerate(EXAMPLE_QUESTIONS[category], start=1):
                st.markdown(f"**예시 {number}.** {example}")

    with st.form("legal_question_form", clear_on_submit=False):
        question = st.text_area(
            "상황을 구체적으로 적어주세요",
            height=180,
            max_chars=2000,
            placeholder=(
                "이름·전화번호·상세 주소 등 개인정보는 입력하지 않는 것을 권장합니다. "
                "입력된 식별정보는 외부 호출 전에 마스킹됩니다."
            ),
        )
        with st.expander("추가로 가릴 이름·회사명 입력 (선택)"):
            sensitive_terms = st.text_input(
                "쉼표로 구분",
                placeholder="홍길동, 세이프로 주식회사",
                label_visibility="collapsed",
            )
            st.caption("입력한 단어는 `[CUSTOM_N]`으로 바뀐 뒤 검색과 답변 생성에 사용됩니다.")
        submitted = st.form_submit_button(
            "관련 법령·판례 검토하기",
            type="primary",
            use_container_width=True,
            disabled=not ready,
        )

    if not submitted:
        st.divider()
        st.caption(
            "SafeLaw는 법률정보 검색 보조 도구입니다. 변호사의 법률 자문을 대체하거나 승소 가능성을 예측하지 않습니다."
        )
        return
    if category is None:
        st.warning("상담 받으실 분야를 선택해 주세요.")
        return
    if not question.strip():
        st.warning("검토할 상황을 입력해 주세요.")
        return

    try:
        privacy = PrivacyGuard().redact(
            question,
            parse_sensitive_terms(sensitive_terms),
        )
        if "safelaw_pipeline" not in st.session_state:
            st.session_state.safelaw_pipeline = build_pipeline(settings, INDEX_PATH)
        pipeline = st.session_state.safelaw_pipeline
        with st.spinner("개인정보를 가린 뒤 관련 법령·판례와 근거 문구를 검증하고 있습니다..."):
            answer = pipeline.answer(
                privacy.sanitized_text,
                category=category,
                top_k=5,
            )
    except UiConfigurationError as exc:
        st.error(str(exc))
        return
    except (RuntimeError, ValueError):
        st.error("요청을 처리하지 못했습니다. 설정과 네트워크 상태를 확인한 뒤 다시 시도해 주세요.")
        return

    st.divider()
    _render_result(
        st,
        answer,
        original_text=question,
        sanitized_text=privacy.sanitized_text,
        redaction_count=privacy.redaction_count,
    )

