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
from legal_rag.rag.case_selection import CaseCandidateSelector
from legal_rag.rag.citations import CaseEvidence
from legal_rag.rag.condition_search import ConditionSearchError, StatuteConditionSearch
from legal_rag.rag.retrieval import CombinedLegalRetriever, ExpandedStatuteRetriever, LegalQueryExpander
from legal_rag.rag.statute_catalog import StatuteCatalog, StatuteItem
from legal_rag.security.redaction import PrivacyGuard


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDEX_PATH = PROJECT_ROOT / "data" / "indexes" / "statutes"
STATUTE_CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "statute_chunks.json"
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


EXAMPLE_CONDITIONS = {
    LegalCategory.LABOR: "해고할 때 회사가 지켜야 하는 통보 절차를 정한 조문",
    LegalCategory.HOUSING_LEASE: "보증금을 돌려받지 못한 채 이사할 때 권리를 지키는 조문",
    LegalCategory.INHERITANCE: "상속을 포기하거나 한정승인할 수 있는 기간을 정한 조문",
}

CHAT_STATE_KEY = "article_chats"
SELECTED_ARTICLE_KEY = "selected_article_id"
CONDITION_RESULT_KEY = "article_condition_result"


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


def chat_history(state: Any, item_id: str) -> list[dict[str, Any]]:
    """조문별 대화 기록을 분리해 반환한다. 기록은 현재 세션 메모리에만 존재한다."""

    if CHAT_STATE_KEY not in state:
        state[CHAT_STATE_KEY] = {}
    return state[CHAT_STATE_KEY].setdefault(item_id, [])


def article_question(article_label: str, sanitized_question: str) -> str:
    """선택 조문을 질문 앞에 밝혀 검색과 답변이 그 조문을 중심으로 이뤄지게 한다."""

    return f"[선택 조문: {article_label}] {sanitized_question.strip()}"


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
                    selector=CaseCandidateSelector(answer_llm),
                    chunk_max_chars=settings.case_chunk_size,
                    chunk_overlap_chars=settings.case_chunk_overlap,
                )
            return StatuteRagPipeline(
                CombinedLegalRetriever(statute_retriever, case_retriever, enricher),
                answer_llm,
            )
    return StatuteRagPipeline(statute_retriever, answer_llm)


def build_condition_search(
    settings: Settings,
    catalog: StatuteCatalog,
    index_path: Path = INDEX_PATH,
) -> StatuteConditionSearch:
    ready, message = runtime_readiness(settings, index_path)
    if not ready:
        raise UiConfigurationError(message)
    assert settings.gms_key is not None
    store = ChromaStatuteVectorStore(index_path)
    if store.count == 0:
        raise UiConfigurationError("법령 색인이 비어 있습니다. build_statute_index.py를 실행해 주세요.")
    retriever = ExpandedStatuteRetriever(
        GmsEmbeddingClient(
            settings.gms_key,
            model_name=settings.gms_embedding_model,
            base_url=settings.gms_base_url,
        ),
        store,
        LegalQueryExpander(
            GmsChatClient(settings.gms_key, model_name=settings.query_model, base_url=settings.gms_base_url)
        ),
    )
    # 조건 선별은 JSON 형식 안정성이 중요해 답변 생성 모델을 사용한다.
    selector = GmsChatClient(settings.gms_key, model_name=settings.answer_model, base_url=settings.gms_base_url)
    return StatuteConditionSearch(retriever, selector, catalog)


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

    situation_tab, article_tab = st.tabs(["상황으로 검토하기", "조문 찾기·조문별 상담"])
    with situation_tab:
        _render_situation_review(st, settings, ready)
    with article_tab:
        _render_article_explorer(st, settings, ready)


def _render_situation_review(st: Any, settings: Settings, ready: bool) -> None:
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
                top_k=settings.rag_top_k,
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



def _load_catalog(st: Any) -> StatuteCatalog:
    if "safelaw_catalog" not in st.session_state:
        st.session_state.safelaw_catalog = StatuteCatalog.from_chunk_file(STATUTE_CHUNKS_PATH)
    return st.session_state.safelaw_catalog


def _select_article(state: Any, item_id: str) -> None:
    state[SELECTED_ARTICLE_KEY] = item_id


def _sync_picked_article(state: Any, widget_key: str) -> None:
    if state.get(widget_key):
        state[SELECTED_ARTICLE_KEY] = state[widget_key]


def _render_condition_search(st: Any, settings: Settings, ready: bool, category: LegalCategory,
                             catalog: StatuteCatalog, sensitive_terms: tuple[str, ...]) -> None:
    with st.form("condition_search_form", clear_on_submit=False):
        condition = st.text_input(
            "찾고 싶은 조문의 조건을 자연어로 적어주세요",
            max_chars=300,
            placeholder=f"예: {EXAMPLE_CONDITIONS[category]}",
        )
        searched = st.form_submit_button(
            "조건에 맞는 조문 찾기",
            type="primary",
            use_container_width=True,
            disabled=not ready,
        )

    if searched:
        if not condition.strip():
            st.warning("찾고 싶은 조문의 조건을 입력해 주세요.")
        else:
            try:
                privacy = PrivacyGuard().redact(condition, sensitive_terms)
                if "safelaw_condition_search" not in st.session_state:
                    st.session_state.safelaw_condition_search = build_condition_search(settings, catalog)
                with st.status("후보 조문을 검색하고 조건에 맞는 조문만 고르고 있습니다...") as status:
                    result = st.session_state.safelaw_condition_search.search(
                        privacy.sanitized_text, category=category
                    )
                    status.update(
                        label=f"후보 {len(result.candidates)}개 중 {len(result.matches)}개 조문을 골랐습니다.",
                        state="complete",
                    )
                st.session_state[CONDITION_RESULT_KEY] = {
                    "category": category.value,
                    "condition": privacy.sanitized_text,
                    "candidate_count": len(result.candidates),
                    "matches": [(match.item.item_id, match.reason) for match in result.matches],
                }
            except UiConfigurationError as exc:
                st.error(str(exc))
            except ConditionSearchError:
                st.error("조건에 맞는 조문을 고르지 못했습니다. 조건을 조금 바꿔 다시 시도해 주세요.")
            except (RuntimeError, ValueError):
                st.error("요청을 처리하지 못했습니다. 설정과 네트워크 상태를 확인한 뒤 다시 시도해 주세요.")

    stored = st.session_state.get(CONDITION_RESULT_KEY)
    if not stored or stored["category"] != category.value:
        return
    st.caption(f"조건: {stored['condition']}")
    if not stored["matches"]:
        st.info(
            f"후보 {stored['candidate_count']}개 중 조건에 맞는 조문이 없습니다. "
            "조건을 더 구체적으로 적거나 아래 목록에서 직접 선택해 주세요."
        )
        return
    columns = st.columns(2)
    for index, (item_id, reason) in enumerate(stored["matches"]):
        item = catalog.find(item_id)
        if item is None:
            continue
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"**{item.label}**")
                if reason:
                    st.caption(f"선정 이유: {reason}")
                st.write(" ".join(item.text.split())[:120] + "…")
                st.button(
                    "이 조문으로 상담하기",
                    key=f"pick_article_{item_id}",
                    on_click=_select_article,
                    args=(st.session_state, item_id),
                    use_container_width=True,
                )


def _render_article_chat(st: Any, settings: Settings, ready: bool, item: StatuteItem,
                         sensitive_terms: tuple[str, ...]) -> None:
    st.markdown(f"### 💬 {item.label}")
    st.caption(f"시행일 {item.effective_date} · [국가법령정보센터 원문]({item.source_url})")
    with st.expander("조문 원문 보기"):
        st.text(item.text)
    st.caption("이 조문은 질문마다 근거에 항상 포함됩니다. 대화 기록은 조문별로 따로 보관되며 세션을 닫으면 사라집니다.")

    history = chat_history(st.session_state, item.item_id)
    for message in history:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                presentation = STATUS_PRESENTATIONS[AnswerStatus(message["status"])]
                st.caption(f"{presentation.icon} {presentation.title} · 상태 코드 `{message['status']}`")
            st.markdown(message["content"])
            if message.get("redaction_count"):
                st.caption(f"개인정보 {message['redaction_count']}건을 가린 문장입니다.")

    prompt = st.chat_input(
        "이 조문에 대해 궁금한 상황을 질문하세요",
        key="article_chat_input",
        disabled=not ready,
        max_chars=2000,
    )
    if not prompt:
        return

    privacy = PrivacyGuard().redact(prompt, sensitive_terms)
    user_message = {
        "role": "user",
        "content": privacy.sanitized_text,
        "redaction_count": privacy.redaction_count,
    }
    history.append(user_message)
    with st.chat_message("user"):
        st.markdown(user_message["content"])
        if privacy.redaction_count:
            st.caption(f"개인정보 {privacy.redaction_count}건을 가린 문장입니다.")

    with st.chat_message("assistant"):
        try:
            if "safelaw_pipeline" not in st.session_state:
                st.session_state.safelaw_pipeline = build_pipeline(settings, INDEX_PATH)
            with st.spinner("선택 조문과 관련 법령·판례로 근거를 검증하고 있습니다..."):
                answer = st.session_state.safelaw_pipeline.answer(
                    article_question(item.label, privacy.sanitized_text),
                    category=item.category,
                    top_k=settings.rag_top_k,
                    pinned_hits=item.pinned_hits(),
                )
        except UiConfigurationError as exc:
            history.pop()
            st.error(str(exc))
            return
        except (RuntimeError, ValueError):
            history.pop()
            st.error("요청을 처리하지 못했습니다. 설정과 네트워크 상태를 확인한 뒤 다시 시도해 주세요.")
            return
        presentation = STATUS_PRESENTATIONS[answer.status]
        st.caption(f"{presentation.icon} {presentation.title} · 상태 코드 `{answer.status.value}`")
        st.markdown(answer.content)
    history.append({"role": "assistant", "content": answer.content, "status": answer.status.value})


def _render_article_explorer(st: Any, settings: Settings, ready: bool) -> None:
    st.markdown(
        "법령 조문을 하나의 항목으로 보고, 조건에 맞는 조문을 찾은 뒤 그 조문을 중심으로 질문합니다."
    )
    category = st.selectbox(
        "상담 분야",
        options=[None, *list(LegalCategory)],
        index=0,
        format_func=lambda item: (
            "조문을 찾을 분야를 선택해 주세요" if item is None else CATEGORY_LABELS[item]
        ),
        key="article_category",
    )
    if category is None:
        st.info("분야를 선택하면 조건으로 조문을 찾거나 목록에서 직접 고를 수 있습니다.")
        return

    try:
        catalog = _load_catalog(st)
    except (OSError, ValueError, KeyError):
        st.error("조문 데이터셋을 읽지 못했습니다. build_statute_chunks.py를 먼저 실행해 주세요.")
        return

    with st.expander("추가로 가릴 이름·회사명 입력 (선택)"):
        extra_terms = st.text_input(
            "쉼표로 구분",
            placeholder="홍길동, 세이프로 주식회사",
            label_visibility="collapsed",
            key="article_sensitive_terms",
        )
        st.caption("조건 검색과 조문별 채팅 모두에서 입력한 단어를 `[CUSTOM_N]`으로 바꾼 뒤 외부 모델에 전달합니다.")
    sensitive_terms = parse_sensitive_terms(extra_terms)

    _render_condition_search(st, settings, ready, category, catalog, sensitive_terms)

    items = catalog.items(category)
    picker_key = f"article_picker_{category.value}"
    st.selectbox(
        f"또는 목록에서 직접 선택 ({len(items)}개 조문)",
        options=[None, *[item.item_id for item in items]],
        format_func=lambda item_id: (
            "조문을 선택해 주세요" if item_id is None else catalog.get(item_id).label
        ),
        key=picker_key,
        on_change=_sync_picked_article,
        args=(st.session_state, picker_key),
    )

    selected = catalog.find(st.session_state.get(SELECTED_ARTICLE_KEY, ""))
    if selected is None or selected.category is not category:
        st.divider()
        st.caption(
            "SafeLaw는 법률정보 검색 보조 도구입니다. 변호사의 법률 자문을 대체하거나 승소 가능성을 예측하지 않습니다."
        )
        return
    st.divider()
    _render_article_chat(st, settings, ready, selected, sensitive_terms)
