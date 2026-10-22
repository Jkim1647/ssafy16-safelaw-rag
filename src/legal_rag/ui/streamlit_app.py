"""SafeLaw Streamlit 사용자 인터페이스."""

from __future__ import annotations

import re
import time
from collections import Counter
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient
from legal_rag.adapters.gms_llm import GmsChatClient
from legal_rag.adapters.vector_store import ChromaCaseVectorStore, ChromaStatuteVectorStore
from legal_rag.config import Settings
from legal_rag.collectors.court_cases import CourtCaseOpenApiClient
from legal_rag.domain.glossary import find_terms
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.pipeline import AnswerStatus, StatuteRagPipeline
from legal_rag.rag.case_enrichment import IncrementalCaseEnricher
from legal_rag.rag.case_selection import CaseCandidateSelector
from legal_rag.rag.condition_search import ConditionSearchError, StatuteConditionSearch
from legal_rag.rag.issue_checklist import CHECK_STATUSES, IssueChecklist, IssueChecklistBuilder
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
CONSULT_MESSAGES_KEY = "consult_messages"
CONSULTATIONS_KEY = "consultations"
CONSULT_THREAD_KEY = "consult_thread_id"
PENDING_PROMPT_KEY = "consult_pending_prompt"
CHECKLIST_FOCUS_KEY = "consult_checklist_focus"
VIEW_CONSULT = "💬 상담실"
VIEW_ARTICLES = "📚 조문 찾아보기"
USER_AVATAR = "🙋"
ASSISTANT_AVATAR = "⚖️"
SELECTED_ARTICLE_KEY = "selected_article_id"
CONDITION_RESULT_KEY = "article_condition_result"


CHECKLIST_BLOCKED_MESSAGES = {
    AnswerStatus.NO_EVIDENCE: "관련 근거를 찾지 못해 체크리스트를 만들지 않았습니다.",
    AnswerStatus.INSUFFICIENT_EVIDENCE: "검색된 근거만으로는 체크리스트를 만들 수 없어 표시하지 않습니다.",
    AnswerStatus.INVALID_CITATIONS: "체크리스트 항목의 근거를 검증하지 못해 표시하지 않습니다.",
    AnswerStatus.GENERATION_FAILED: "체크리스트 생성 중 오류가 발생해 표시하지 않습니다.",
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


def chat_history(state: Any, item_id: str) -> list[dict[str, Any]]:
    """조문별 대화 기록을 분리해 반환한다. 기록은 현재 세션 메모리에만 존재한다."""

    if CHAT_STATE_KEY not in state:
        state[CHAT_STATE_KEY] = {}
    return state[CHAT_STATE_KEY].setdefault(item_id, [])


def article_question(article_label: str, sanitized_question: str) -> str:
    """선택 조문을 질문 앞에 밝혀 검색과 답변이 그 조문을 중심으로 이뤄지게 한다."""

    return f"[선택 조문: {article_label}] {sanitized_question.strip()}"


def runtime_readiness(settings: Settings, index_path: Path | None = None) -> tuple[bool, str]:
    if not settings.has_gms_key:
        return False, ".env에 GMS_KEY를 설정해 주세요."
    if not (index_path or INDEX_PATH).exists():
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
    search_options = {
        "search_mode": settings.rag_search_mode,
        "mmr_fetch_k": settings.rag_mmr_fetch_k,
        "mmr_lambda": settings.rag_mmr_lambda,
    }
    statute_retriever = ExpandedStatuteRetriever(
        embedder,
        store,
        LegalQueryExpander(query_llm),
        **search_options,
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
                **search_options,
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


def build_checklist_builder(settings: Settings) -> IssueChecklistBuilder:
    if not settings.has_gms_key:
        raise UiConfigurationError(".env에 GMS_KEY를 설정해 주세요.")
    assert settings.gms_key is not None
    # 체크리스트도 인용 검증을 통과해야 하므로 답변 생성 모델을 사용한다.
    return IssueChecklistBuilder(
        GmsChatClient(settings.gms_key, model_name=settings.answer_model, base_url=settings.gms_base_url)
    )


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
    # 로펌 상담실: 호두나무 벽판(사이드바)과 책상(입력창), 석회암 벽, 그 위에 놓인 상담 기록지, 황동 문패.
    st.markdown(
        """
        <style>
        :root { --walnut: #2c1f18; --walnut-light: #3b2a20; --brass: #b08a52; --brass-dark: #8a6a38;
            --counsel: #1f2c3d; --paper: #fcfbf8; --wall: #d5d9dc; --ink-soft: #4b5560; }
        .stApp, [data-testid="stHeader"] { background: var(--wall); }
        .block-container { max-width: 900px; padding-top: 1.4rem; padding-bottom: 7rem; }
        [data-testid="stSidebar"] { background:
            repeating-linear-gradient(90deg, rgba(255,255,255,.018) 0 2px, transparent 2px 11px),
            linear-gradient(180deg, var(--walnut-light), var(--walnut)); }
        [data-testid="stBottom"], [data-testid="stBottom"] > div { background: var(--walnut); }
        [data-testid="stBottom"] { border-top: 3px solid var(--brass-dark); }

        .nameplate { display: flex; flex-direction: column; align-items: center; margin: .2rem 0 1.4rem; }
        .nameplate .plate { position: relative; padding: .8rem 2.8rem .75rem; border-radius: 3px; text-align: center;
            background: linear-gradient(180deg, #dcc08a 0%, #b8925a 50%, #9a7642 100%);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.45), inset 0 -1px 0 rgba(0,0,0,.25),
                0 8px 16px -8px rgba(20,14,8,.6); }
        .nameplate .plate::before, .nameplate .plate::after { content: ""; position: absolute; top: 50%;
            width: 7px; height: 7px; border-radius: 50%; transform: translateY(-50%);
            background: radial-gradient(circle at 35% 35%, #f3e2bb, #6f5226); }
        .nameplate .plate::before { left: .95rem; }
        .nameplate .plate::after { right: .95rem; }
        .nameplate .firm, .nameplate .room { display: block; font-family: "Nanum Myeongjo", serif;
            color: #3a2912; text-shadow: 0 1px 0 rgba(255,240,210,.55); }
        .nameplate .firm { font-size: 1.6rem; font-weight: 800; letter-spacing: .06em; line-height: 1.2; }
        .nameplate .room { font-size: .95rem; font-weight: 700; letter-spacing: .3em; margin-top: .2rem; }
        .nameplate .note { margin: .75rem 0 0; font-size: .88rem; color: var(--ink-soft); text-align: center; }

        .st-key-consult_sheet, .st-key-checklist_panel { background: var(--paper); border-radius: 4px;
            box-shadow: 0 1px 0 rgba(31,44,61,.06), 0 22px 40px -22px rgba(31,44,61,.45); }
        .st-key-consult_sheet { padding: 1.6rem 2rem 1.2rem; }
        .office-steps { display: grid; grid-template-columns: repeat(4, 1fr); margin: 0 0 .9rem;
            border-top: 1px solid #e3ded2; border-bottom: 1px solid #e3ded2; }
        .office-steps span { padding: .55rem .5rem; font-size: .84rem; color: var(--ink-soft); line-height: 1.35; }
        .office-steps b { font-family: "Nanum Myeongjo", serif; font-size: 1rem; color: var(--brass-dark);
            margin-right: .35rem; }
        .privacy-box { background: #f1f2ef; border-radius: 4px; padding: .6rem .85rem; color: #34404b;
            margin: 0 0 1rem; font-size: .88rem; }
        [data-testid="stChatMessage"] { background: transparent; }
        [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) { background: #edf0f4;
            border-radius: 4px; }
        [data-testid="stChatMessage"] h2 { font-size: 1.2rem; margin-top: .2rem; }
        [data-testid="stChatMessage"] h3 { font-size: 1.02rem; }
        div.stButton > button { font-weight: 600; }
        :focus-visible { outline: 2px solid var(--brass) !important; outline-offset: 2px; }

        /* 체크리스트가 있으면 본문을 넓히고 오른쪽 패널을 화면에 고정한다. */
        .block-container:has(.st-key-checklist_panel) { max-width: 1280px; }
        [data-testid="stColumn"]:has(.st-key-checklist_panel) { position: sticky; top: 3.75rem;
            align-self: flex-start; max-height: calc(100vh - 10rem); overflow-y: auto; }
        .st-key-checklist_panel { border-top: 3px solid var(--brass); padding: 1rem 1.1rem; }
        .st-key-checklist_panel h3 { font-size: 1.05rem; }
        @media (max-width: 640px) {
            [data-testid="stColumn"]:has(.st-key-checklist_panel) { position: static; max-height: none; }
            .st-key-consult_sheet { padding: 1.1rem 1rem .8rem; }
            .office-steps { grid-template-columns: repeat(2, 1fr); }
            .nameplate .plate { padding: .7rem 2.2rem .65rem; }
            .nameplate .firm { font-size: 1.35rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_nameplate(st: Any, room: str, note: str) -> None:
    st.markdown(
        f'<div class="nameplate"><div class="plate"><span class="firm">SafeLaw</span>'
        f'<span class="room">{room}</span></div><p class="note">{note}</p></div>',
        unsafe_allow_html=True,
    )


@dataclass(frozen=True, slots=True)
class SidebarOptions:
    view: str
    category: LegalCategory | None
    sensitive_terms: tuple[str, ...]
    include_checklist: bool


def _start_new_consultation(state: Any) -> None:
    thread_id = uuid.uuid4().hex
    if CONSULTATIONS_KEY not in state:
        state[CONSULTATIONS_KEY] = {}
    state[CONSULTATIONS_KEY][thread_id] = {"title": "", "category": None, "messages": [], "updated": time.time()}
    _open_consultation(state, thread_id)


def _open_consultation(state: Any, thread_id: str) -> None:
    """지난 상담을 다시 연다. 같은 thread_id라 LangGraph 체크포인터의 맥락도 이어진다."""

    entry = state[CONSULTATIONS_KEY][thread_id]
    state[CONSULT_THREAD_KEY] = thread_id
    state[CONSULT_MESSAGES_KEY] = entry["messages"]
    if entry["category"]:
        state["consult_category"] = LegalCategory(entry["category"])


def _delete_consultation(state: Any, thread_id: str) -> None:
    state.get(CONSULTATIONS_KEY, {}).pop(thread_id, None)
    pipeline = state.get("safelaw_pipeline")
    if pipeline is not None:
        pipeline.forget_conversation(thread_id)
    if state.get(CONSULT_THREAD_KEY) == thread_id:
        _start_new_consultation(state)


def _render_consultation_history(st: Any) -> None:
    consultations = st.session_state.get(CONSULTATIONS_KEY, {})
    past = sorted(
        ((thread_id, entry) for thread_id, entry in consultations.items() if entry["messages"]),
        key=lambda item: item[1]["updated"],
        reverse=True,
    )
    if not past:
        return
    st.markdown("**지난 상담**")
    current = st.session_state.get(CONSULT_THREAD_KEY)
    for thread_id, entry in past:
        turns = sum(1 for message in entry["messages"] if message["role"] == "user")
        category = CATEGORY_LABELS[LegalCategory(entry["category"])] if entry["category"] else ""
        open_column, delete_column = st.columns([5, 1], vertical_alignment="center")
        open_column.button(
            entry["title"],
            key=f"open_{thread_id}",
            on_click=_open_consultation,
            args=(st.session_state, thread_id),
            type="primary" if thread_id == current else "secondary",
            help=f"{category} · 질문 {turns}개",
            use_container_width=True,
        )
        delete_column.button(
            "🗑️",
            key=f"delete_{thread_id}",
            on_click=_delete_consultation,
            args=(st.session_state, thread_id),
            type="tertiary",
            help="이 상담 기록을 지웁니다",
        )


def _render_sidebar(st: Any, settings: Settings, ready: bool, readiness_message: str) -> SidebarOptions:
    with st.sidebar:
        st.subheader("⚖️ SafeLaw")
        st.caption("개인정보 보호형 생활법률 상담실")
        if ready:
            st.success("시스템 준비 완료", icon="✅")
        else:
            st.error(readiness_message, icon="⚠️")

        view = st.radio("메뉴", [VIEW_CONSULT, VIEW_ARTICLES], key="safelaw_view")
        category = None
        include_checklist = True
        if view == VIEW_CONSULT:
            category = st.selectbox(
                "상담 분야",
                options=[None, *list(LegalCategory)],
                format_func=lambda item: "상담 분야를 골라 주세요" if item is None else CATEGORY_LABELS[item],
                key="consult_category",
            )
            include_checklist = st.toggle(
                "내 상황 쟁점 체크리스트 함께 보기",
                value=True,
                help="답변마다 법령·판례가 따지는 판단 요소를 근거 번호와 함께 정리합니다.",
            )
            turns = sum(1 for item in st.session_state.get(CONSULT_MESSAGES_KEY, []) if item["role"] == "user")
            st.button(
                "🆕 새 상담 시작",
                key="new_consultation",
                on_click=_start_new_consultation,
                args=(st.session_state,),
                use_container_width=True,
                disabled=turns == 0,
            )
            if turns:
                st.caption(f"이번 상담에서 {turns}번 질문했어요. 이어서 묻는 질문은 앞선 상담 내용을 함께 고려해요.")
            _render_consultation_history(st)

        terms = st.text_input(
            "추가로 가릴 이름·회사명 (쉼표로 구분)",
            placeholder="홍길동, 세이프로 주식회사",
            key="sensitive_terms_input",
            help="입력한 단어는 [CUSTOM_N]으로 바뀐 뒤 검색과 답변 생성에 사용됩니다.",
        )
        st.divider()
        with st.expander("상담 가능한 분야"):
            for item, label in CATEGORY_LABELS.items():
                st.markdown(f"- **{label}**  \n  {CATEGORY_HELP[item]}")
        st.caption(
            "전화번호·주민등록번호·이메일·주소와 직접 지정한 단어는 외부 모델 호출 전에 로컬에서 가립니다. "
            "상담 원문과 대화 기록은 이 세션의 메모리에만 있고 파일이나 Vector DB에 저장하지 않습니다."
        )
        with st.expander("실행 정보"):
            st.code(
                f"환경: {settings.app_env}\n"
                f"검색어 변환 모델: {settings.query_model}\n"
                f"답변 생성 모델: {settings.answer_model}\n"
                f"임베딩 모델: {settings.gms_embedding_model}\n"
                f"검색 방식: {settings.rag_search_mode} · Top-k {settings.rag_top_k}",
                language="text",
            )
            st.caption(
                "판례 자동 보강: "
                + ("활성화" if settings.has_law_api_key else "비활성화 (LAW_API_OC 미설정)")
            )
    return SidebarOptions(view, category, parse_sensitive_terms(terms), include_checklist)


def _render_answer(st: Any, message: dict[str, Any], focused_token: str | None = None) -> None:
    status = AnswerStatus(message["status"])
    presentation = STATUS_PRESENTATIONS[status]
    st.caption(f"{presentation.icon} {presentation.title} · 상태 코드 `{status.value}`")
    if status is AnswerStatus.ANSWERED:
        st.markdown(message["content"])
    else:
        st.warning(message["content"])
        st.caption("상황을 조금 더 구체적으로 말씀해 주시거나 상담 분야를 확인해 주세요.")
    if message.get("checklist") is not None:
        _render_checklist_summary(st, message, focused=message["token"] == focused_token)


def _checklist_summary(checklist: IssueChecklist) -> str:
    if not checklist.is_ready:
        return "📋 이번 답변은 쟁점 체크리스트를 만들지 못했어요."
    counts = Counter(item.status for item in checklist.items)
    parts = " · ".join(f"{icon} {label} {counts[key]}" for key, (icon, label) in CHECK_STATUSES.items() if counts[key])
    return f"📋 쟁점 체크리스트 {len(checklist.items)}개 · {parts}"


def _render_checklist_summary(st: Any, message: dict[str, Any], *, focused: bool) -> None:
    """대화 안에는 요약만 두고, 체크할 수 있는 전체 목록은 오른쪽 패널에 둔다."""

    with st.container(border=True):
        st.markdown(_checklist_summary(message["checklist"]))
        if focused:
            st.caption("오른쪽 패널에서 항목별로 확인할 수 있어요.")
        else:
            st.button(
                "오른쪽 패널에서 보기",
                key=f"focus_{message['token']}",
                on_click=_focus_checklist,
                args=(st.session_state, message["token"]),
            )


def _focus_checklist(state: Any, token: str) -> None:
    state[CHECKLIST_FOCUS_KEY] = token


def _focused_checklist_message(state: Any, messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """사용자가 고른 답변의 체크리스트, 없으면 가장 최근 답변의 체크리스트를 고른다."""

    candidates = [message for message in messages if message.get("checklist") is not None]
    if not candidates:
        return None
    focus = state.get(CHECKLIST_FOCUS_KEY)
    return next((message for message in candidates if message["token"] == focus), candidates[-1])


def _render_checklist_panel(st: Any, messages: list[dict[str, Any]], focused: dict[str, Any]) -> None:
    answers = [message for message in messages if message["role"] == "assistant"]
    with st.container(key="checklist_panel"):
        st.caption(f"{answers.index(focused) + 1}번째 답변 기준")
        _render_issue_checklist(st, focused["checklist"], focused["token"])


def _render_user_turn(st: Any, message: dict[str, Any]) -> None:
    st.markdown(message["content"])
    if message["redaction_count"]:
        st.caption(f"🔒 개인정보 {message['redaction_count']}건을 가린 뒤 전달했어요.")
        with st.expander("원문과 외부 모델 전달문 비교"):
            original_column, sanitized_column = st.columns(2)
            with original_column:
                st.markdown("**입력 원문**")
                st.caption("현재 브라우저·로컬 앱에서만 확인")
                st.write(message["original"])
            with sanitized_column:
                st.markdown("**외부 모델 전달문**")
                st.caption("검색·임베딩·LLM에 사용")
                st.write(message["content"])


def _consult_greeting(category: LegalCategory | None) -> str:
    if category is None:
        return (
            "안녕하세요, **SafeLaw 생활법률 상담실**입니다. 왼쪽에서 **상담 분야**를 먼저 골라 주세요. "
            "그다음 어떤 일이 있었는지 편하게 말씀해 주시면 관련 법령과 판례 원문으로 확인되는 내용만 안내해 드려요."
        )
    return (
        f"**{CATEGORY_LABELS[category]}** 상담을 도와드릴게요. 어떤 일이 있었는지 아래 입력창에 말씀해 주세요. "
        "답변을 보신 뒤 궁금한 점을 이어서 물으시면 앞선 상담 내용을 함께 고려해 답해 드려요."
    )


def _queue_prompt(state: Any, prompt: str) -> None:
    state[PENDING_PROMPT_KEY] = prompt


def _render_consultation_room(st: Any, settings: Settings, ready: bool, options: SidebarOptions) -> None:
    _render_nameplate(st, "생활법률 상담실", "법령과 공개 판례 원문으로 확인되는 내용만 안내합니다")

    if CONSULT_THREAD_KEY not in st.session_state:
        _start_new_consultation(st.session_state)
    messages: list[dict[str, Any]] = st.session_state[CONSULT_MESSAGES_KEY]
    focused = _focused_checklist_message(st.session_state, messages)
    focused_token = focused["token"] if focused else None

    # 입력창보다 먼저 대화 영역을 만들어 새 질문과 답변도 대화 흐름 안에 쌓이게 한다.
    # 대화는 벽 위에 놓인 상담 기록지(sheet) 안에 쌓인다.
    if focused is None:
        sheet = st.container(key="consult_sheet")
    else:
        chat_area, panel_area = st.columns([3, 2], gap="large")
        with panel_area:
            _render_checklist_panel(st, messages, focused)
        sheet = chat_area.container(key="consult_sheet")
    with sheet:
        st.markdown(
            '<div class="office-steps"><span><b>1</b>상담 분야 선택</span><span><b>2</b>상황 말씀하기</span>'
            '<span><b>3</b>근거와 함께 안내</span><span><b>4</b>이어서 질문하기</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="privacy-box">🔒 정확한 이름·전화번호·상세 주소는 가능하면 적지 마세요. '
            '적더라도 외부 모델에 보내기 전에 자동으로 가립니다.</div>',
            unsafe_allow_html=True,
        )
        conversation = st.container()
    with conversation:
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            st.markdown(_consult_greeting(options.category))
            if options.category is not None and not messages:
                st.caption("이런 상황을 많이 물어보세요")
                for index, example in enumerate(EXAMPLE_QUESTIONS[options.category]):
                    st.button(
                        example,
                        key=f"example_{options.category.value}_{index}",
                        on_click=_queue_prompt,
                        args=(st.session_state, example),
                        use_container_width=True,
                        disabled=not ready,
                    )
        for message in messages:
            avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
            with st.chat_message(message["role"], avatar=avatar):
                if message["role"] == "user":
                    _render_user_turn(st, message)
                else:
                    _render_answer(st, message, focused_token)

    typed = st.chat_input(
        "상황이나 궁금한 점을 입력하세요. 개인정보는 자동으로 가려집니다.",
        key="consult_chat_input",
        disabled=not ready,
        max_chars=2000,
    )
    prompt = typed or st.session_state.pop(PENDING_PROMPT_KEY, None)
    if not prompt:
        st.caption("SafeLaw는 법률정보 검색 보조 도구입니다. 변호사의 법률 자문을 대체하거나 승소 가능성을 예측하지 않습니다.")
        return
    if options.category is None:
        with conversation, st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            st.warning("왼쪽에서 상담 분야를 먼저 골라 주세요.")
        return
    _run_consultation_turn(st, settings, options, conversation, messages, prompt)


def _run_consultation_turn(st: Any, settings: Settings, options: SidebarOptions, conversation: Any,
                           messages: list[dict[str, Any]], prompt: str) -> None:
    assert options.category is not None
    privacy = PrivacyGuard().redact(prompt, options.sensitive_terms)
    user_message = {
        "role": "user",
        "content": privacy.sanitized_text,
        "original": prompt,
        "redaction_count": privacy.redaction_count,
    }
    with conversation:
        with st.chat_message("user", avatar=USER_AVATAR):
            _render_user_turn(st, user_message)
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            try:
                if "safelaw_pipeline" not in st.session_state:
                    st.session_state.safelaw_pipeline = build_pipeline(settings, INDEX_PATH)
                with st.status("상담 내용을 확인하고 있어요…", expanded=False) as status:
                    status.write(f"🔒 개인정보 {privacy.redaction_count}건을 가렸어요.")
                    status.update(label="관련 법령과 판례를 찾고 근거 문구를 검증하고 있어요…")
                    answer, evidence = st.session_state.safelaw_pipeline.converse(
                        privacy.sanitized_text,
                        thread_id=st.session_state[CONSULT_THREAD_KEY],
                        category=options.category,
                        top_k=settings.rag_top_k,
                    )
                    checklist = None
                    if options.include_checklist and evidence:
                        status.update(label="같은 근거로 쟁점 체크리스트를 정리하고 있어요…")
                        if "safelaw_checklist_builder" not in st.session_state:
                            st.session_state.safelaw_checklist_builder = build_checklist_builder(settings)
                        checklist = st.session_state.safelaw_checklist_builder.build(
                            privacy.sanitized_text, options.category, evidence
                        )
                    status.update(label="답변을 준비했어요", state="complete")
            except UiConfigurationError as exc:
                st.error(str(exc))
                return
            except (RuntimeError, ValueError):
                st.error("요청을 처리하지 못했습니다. 설정과 네트워크 상태를 확인한 뒤 다시 시도해 주세요.")
                return
            assistant_message = {
                "role": "assistant",
                "status": answer.status.value,
                "content": answer.content,
                "checklist": checklist,
                "token": uuid.uuid4().hex,
            }
            _render_answer(st, assistant_message, assistant_message["token"])
    if checklist is not None:
        st.session_state[CHECKLIST_FOCUS_KEY] = assistant_message["token"]
    # 대화 기록은 현재 세션 메모리에만 둔다. 원문은 화면 비교용으로만 보관한다.
    messages.extend((user_message, assistant_message))
    entry = st.session_state[CONSULTATIONS_KEY][st.session_state[CONSULT_THREAD_KEY]]
    if not entry["title"]:
        # 목록 제목도 마스킹된 첫 질문으로 만든다.
        first = user_message["content"]
        entry["title"] = first if len(first) <= 24 else first[:24] + "…"
    entry["category"] = options.category.value
    entry["updated"] = time.time()
    # 사이드바(질문 수, 새 상담 버튼)는 이 턴보다 먼저 그려졌으므로 기록을 반영해 다시 그린다.
    st.rerun()


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("Streamlit을 사용하려면 'pip install -e .'을 실행하세요.") from exc

    st.set_page_config(
        page_title="SafeLaw | 생활법률 상담실",
        page_icon="⚖️",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    _inject_styles(st)

    settings = Settings.from_environment()
    ready, readiness_message = runtime_readiness(settings)
    options = _render_sidebar(st, settings, ready, readiness_message)
    if options.view == VIEW_CONSULT:
        _render_consultation_room(st, settings, ready, options)
    else:
        _render_article_explorer(st, settings, ready, options.sensitive_terms)


def _render_issue_checklist(st: Any, checklist: IssueChecklist, token: str) -> None:
    st.subheader("내 상황 쟁점 체크리스트")
    st.caption(
        "검색된 법령·판례가 요구하는 판단 요소마다 입력한 상황에 그 사실이 나와 있는지만 표시합니다. "
        "요건 충족이나 결과를 판단한 것이 아니며, 확인한 항목은 직접 체크해 보세요."
    )
    if not checklist.is_ready:
        st.info(CHECKLIST_BLOCKED_MESSAGES[checklist.status])
        return

    checked = 0
    explained: set[str] = set()
    for index, item in enumerate(checklist.items):
        icon, label = CHECK_STATUSES[item.status]
        citations = " ".join(f"[근거 {citation_id}]" for citation_id in item.claim.citation_ids)
        with st.container(border=True):
            st.markdown(f"{icon} **{label}** · {item.claim.text} {citations}")
            if st.checkbox(item.check_question, key=f"issue_check_{token}_{index}"):
                checked += 1
            quotes = " / ".join(
                f"[근거 {quote.citation_id}] “{quote.quote}”" for quote in item.claim.evidence_quotes
            )
            st.caption(f"근거 문구: {quotes}")
            # 같은 용어는 처음 나온 항목에서만 풀어 준다.
            terms = [
                (term, meaning)
                for term, meaning in find_terms(f"{item.claim.text} {item.check_question} {quotes}")
                if term not in explained
            ]
            if terms:
                explained.update(term for term, _ in terms)
                st.caption("  \n".join(f"📖 **{term}**: {meaning}" for term, meaning in terms))
    st.progress(checked / len(checklist.items), text=f"확인한 항목 {checked}/{len(checklist.items)}")
    if explained:
        st.caption("📖 용어 풀이는 이해를 돕는 일반적인 설명이에요. 내 상황에 어떻게 적용되는지는 근거 원문과 함께 확인하세요.")
    if checklist.dropped_count:
        st.caption(f"근거 문구를 검증하지 못한 {checklist.dropped_count}개 항목은 표시하지 않았습니다.")
    with st.expander("체크리스트 근거 보기"):
        for source in checklist.sources:
            st.markdown(f"- [근거 {source.citation_id}] [{source.label}]({source.source_url})")


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
    # 입력창보다 먼저 대화 영역을 만들어, 방금 보낸 질문과 답변도 입력창 위에 그려지게 한다.
    messages_area = st.container()
    with messages_area:
        _render_chat_messages(st, history)

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
    with messages_area, st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(user_message["content"])
        if privacy.redaction_count:
            st.caption(f"개인정보 {privacy.redaction_count}건을 가린 문장입니다.")

    with messages_area, st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
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


def _render_chat_messages(st: Any, history: list[dict[str, Any]]) -> None:
    for message in history:
        with st.chat_message(message["role"], avatar=USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR):
            if message["role"] == "assistant":
                presentation = STATUS_PRESENTATIONS[AnswerStatus(message["status"])]
                st.caption(f"{presentation.icon} {presentation.title} · 상태 코드 `{message['status']}`")
            st.markdown(message["content"])
            if message.get("redaction_count"):
                st.caption(f"개인정보 {message['redaction_count']}건을 가린 문장입니다.")


def _render_article_explorer(st: Any, settings: Settings, ready: bool, sensitive_terms: tuple[str, ...]) -> None:
    _render_nameplate(st, "조문 열람실", "조건으로 조문을 찾고, 그 조문을 고정 근거로 두고 질문합니다")
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
