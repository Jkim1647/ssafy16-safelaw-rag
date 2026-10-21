"""SafeLaw Streamlit 사용자 인터페이스."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient
from legal_rag.adapters.gms_llm import GmsChatClient
from legal_rag.adapters.vector_store import ChromaStatuteVectorStore
from legal_rag.config import Settings
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.pipeline import AnswerStatus, GroundedAnswer, StatuteRagPipeline
from legal_rag.rag.retrieval import ExpandedStatuteRetriever, LegalQueryExpander
from legal_rag.security.redaction import PrivacyGuard


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDEX_PATH = PROJECT_ROOT / "data" / "indexes" / "statutes"

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
    LegalCategory.LABOR: "회사에서 카카오톡으로 내일부터 나오지 말라고 했어요.",
    LegalCategory.HOUSING_LEASE: "집이 경매로 넘어가면 전세보증금을 먼저 받을 수 있나요?",
    LegalCategory.INHERITANCE: "부모님이 돌아가셨는데 빚이 더 많으면 언제까지 상속을 포기해야 하나요?",
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
    llm = GmsChatClient(
        settings.gms_key,
        model_name=settings.gms_chat_model,
        base_url=settings.gms_base_url,
    )
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
        LegalQueryExpander(llm),
    )
    return StatuteRagPipeline(retriever, llm)


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
                f"채팅 모델: {settings.gms_chat_model}\n"
                f"임베딩 모델: {settings.gms_embedding_model}",
                language="text",
            )


def _render_result(st: Any, answer: GroundedAnswer, redaction_count: int) -> None:
    presentation = STATUS_PRESENTATIONS[answer.status]
    st.subheader("검토 결과")
    message = f"{presentation.icon} {presentation.title}"
    getattr(st, presentation.level)(message)
    st.caption(
        f"개인정보 마스킹 {redaction_count}건 · 검색 근거 {answer.retrieved_count}건 · "
        f"상태 코드 `{answer.status.value}`"
    )

    if answer.is_answered:
        st.markdown(answer.content)
        if answer.sources:
            with st.expander("근거 링크만 모아보기"):
                for source in answer.sources:
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
    st.markdown('<div class="safelaw-title">상황을 적으면 관련 법령부터 확인합니다</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="safelaw-subtitle">검색된 법령 원문으로 검증할 수 있는 내용만 안내하고, 근거가 부족하면 답변하지 않습니다.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="privacy-box">🔒 입력한 개인정보는 외부 호출 전에 마스킹됩니다. '
        '정확한 이름·전화번호·상세 주소는 가능하면 입력하지 마세요.</div>',
        unsafe_allow_html=True,
    )

    with st.form("legal_question_form", clear_on_submit=False):
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
            key="legal_category_v2",
        )
        if category is not None:
            st.caption(f"예시: {EXAMPLE_QUESTIONS[category]}")
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
            "관련 법령 검토하기",
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
        with st.spinner("개인정보를 가린 뒤 관련 법령과 근거 문구를 검증하고 있습니다..."):
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
    _render_result(st, answer, privacy.redaction_count)

