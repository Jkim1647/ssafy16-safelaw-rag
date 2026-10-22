"""SafeLaw 웹 API (심화 F2013).

화면(HTML·CSS·JavaScript)과 서버를 분리하고 JSON 요청·응답으로만 통신한다.
Streamlit과 같은 마스킹·LangGraph 파이프라인·쟁점 체크리스트를 재사용한다.

실행:
    uvicorn legal_rag.web.api:app --port 8000
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from legal_rag.config import Settings
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.citations import CaseEvidence, LegalEvidence
from legal_rag.rag.issue_checklist import CHECK_STATUSES, IssueChecklist
from legal_rag.security.redaction import PrivacyGuard
from legal_rag.ui.streamlit_app import (
    CATEGORY_LABELS,
    CHECKLIST_BLOCKED_MESSAGES,
    EXAMPLE_QUESTIONS,
    STATUS_PRESENTATIONS,
    UiConfigurationError,
    build_checklist_builder,
    build_pipeline,
    runtime_readiness,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
GENERIC_ERROR = "요청을 처리하지 못했습니다. 설정과 네트워크 상태를 확인한 뒤 다시 시도해 주세요."
logger = logging.getLogger(__name__)


class ReviewRequest(BaseModel):
    category: LegalCategory
    question: str = Field(min_length=1, max_length=2000)
    extra_terms: list[str] = Field(default_factory=list, max_length=20)
    include_checklist: bool = True


@dataclass
class WebServices:
    """API가 쓰는 외부 의존성. 테스트에서는 가짜 구현으로 바꾼다."""

    readiness: Callable[[], tuple[bool, str]]
    pipeline: Callable[[], Any]
    checklist_builder: Callable[[], Any]
    top_k: int = 5


def _lazy(factory: Callable[[], Any]) -> Callable[[], Any]:
    lock = threading.Lock()
    holder: dict[str, Any] = {}

    def get() -> Any:
        with lock:
            if "value" not in holder:
                holder["value"] = factory()
            return holder["value"]

    return get


def default_services(settings: Settings | None = None) -> WebServices:
    settings = settings or Settings.from_environment()
    return WebServices(
        readiness=lambda: runtime_readiness(settings),
        pipeline=_lazy(lambda: build_pipeline(settings)),
        checklist_builder=_lazy(lambda: build_checklist_builder(settings)),
        top_k=settings.rag_top_k,
    )


def _source(item: LegalEvidence) -> dict[str, Any]:
    return {
        "citation_id": item.citation_id,
        "kind": "case" if isinstance(item, CaseEvidence) else "statute",
        "label": item.label,
        "url": item.source_url,
    }


def _checklist(checklist: IssueChecklist) -> dict[str, Any]:
    if not checklist.is_ready:
        return {
            "status": checklist.status.value,
            "message": CHECKLIST_BLOCKED_MESSAGES[checklist.status],
            "items": [],
            "sources": [],
            "dropped_count": 0,
        }
    items = []
    for item in checklist.items:
        icon, label = CHECK_STATUSES[item.status]
        items.append({
            "status": item.status,
            "icon": icon,
            "label": label,
            "text": item.claim.text,
            "citations": list(item.claim.citation_ids),
            "check_question": item.check_question,
            "quotes": [{"citation_id": quote.citation_id, "quote": quote.quote} for quote in item.claim.evidence_quotes],
        })
    return {
        "status": checklist.status.value,
        "message": None,
        "items": items,
        "sources": [_source(source) for source in checklist.sources],
        "dropped_count": checklist.dropped_count,
    }


def create_app(services: WebServices | None = None) -> FastAPI:
    app = FastAPI(title="SafeLaw API", docs_url=None, redoc_url=None, openapi_url=None)
    resolved = services or default_services()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        # 입력값을 되돌려 보내지 않도록 FastAPI 기본 오류 본문 대신 고정 문구만 보낸다.
        return JSONResponse(status_code=422, content={"error": "분야와 1~2,000자의 상황을 입력해 주세요."})

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        ready, message = resolved.readiness()
        return {
            "ready": ready,
            "message": message,
            "categories": [
                {"value": category.value, "label": CATEGORY_LABELS[category],
                 "examples": list(EXAMPLE_QUESTIONS[category])}
                for category in LegalCategory
            ],
        }

    @app.post("/api/review")
    def review(request: ReviewRequest) -> JSONResponse:
        ready, message = resolved.readiness()
        if not ready:
            return JSONResponse(status_code=503, content={"error": message})
        try:
            terms = tuple(term.strip() for term in request.extra_terms if term.strip())
            privacy = PrivacyGuard().redact(request.question, terms)
            answer, evidence = resolved.pipeline().answer_with_evidence(
                privacy.sanitized_text, category=request.category, top_k=resolved.top_k
            )
            checklist = None
            if request.include_checklist:
                checklist = _checklist(
                    resolved.checklist_builder().build(privacy.sanitized_text, request.category, evidence)
                )
        except UiConfigurationError as exc:
            return JSONResponse(status_code=503, content={"error": str(exc)})
        except Exception:  # noqa: BLE001 - 화면에는 고정 문구만 보내고 원인은 서버 로그에만 남긴다.
            logger.exception("SafeLaw 검토 요청 처리 실패")
            return JSONResponse(status_code=500, content={"error": GENERIC_ERROR})

        presentation = STATUS_PRESENTATIONS[answer.status]
        return JSONResponse(content={
            "status": answer.status.value,
            "status_label": presentation.title,
            "status_icon": presentation.icon,
            "answered": answer.is_answered,
            "content": answer.content,
            "redaction_count": privacy.redaction_count,
            "sanitized_question": privacy.sanitized_text,
            "retrieved_count": answer.retrieved_count,
            "sources": [_source(source) for source in answer.sources],
            "checklist": checklist,
        })

    return app


def __getattr__(name: str) -> Any:
    # `uvicorn legal_rag.web.api:app`로 실행할 때만 실제 설정으로 앱을 만든다.
    if name == "app":
        value = create_app()
        globals()["app"] = value
        return value
    raise AttributeError(name)
