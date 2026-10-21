"""법령, 판례, 사용자 질문의 공통 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from urllib.parse import urlparse


class LegalCategory(StrEnum):
    LABOR = "labor"
    HOUSING_LEASE = "housing_lease"
    INHERITANCE = "inheritance"


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name}은(는) 빈 값일 수 없습니다.")


def _require_official_url(value: str) -> None:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    allowed = ("law.go.kr", "scourt.go.kr")
    if parsed.scheme != "https" or not any(host == item or host.endswith("." + item) for item in allowed):
        raise ValueError("출처 URL은 law.go.kr 또는 scourt.go.kr의 HTTPS 주소여야 합니다.")


@dataclass(frozen=True, slots=True)
class StatuteDocument:
    law_id: str
    category: LegalCategory
    law_name: str
    article_no: str
    article_title: str
    text: str
    effective_date: date
    source_url: str
    issue_tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("law_id", "law_name", "article_no", "article_title", "text"):
            _require_text(getattr(self, name), name)
        _require_official_url(self.source_url)


@dataclass(frozen=True, slots=True)
class CaseDocument:
    case_id: str
    category: LegalCategory
    case_number: str
    court: str
    decision_date: date
    result: str
    facts: str
    reasoning: str
    source_url: str
    issues: tuple[str, ...] = field(default_factory=tuple)
    related_articles: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("case_id", "case_number", "court", "result", "facts", "reasoning"):
            _require_text(getattr(self, name), name)
        _require_official_url(self.source_url)


@dataclass(frozen=True, slots=True)
class LegalQuestion:
    category: LegalCategory
    sanitized_text: str

    def __post_init__(self) -> None:
        _require_text(self.sanitized_text, "sanitized_text")
        if "\n" * 20 in self.sanitized_text:
            raise ValueError("질문에 비정상적인 연속 개행이 포함되어 있습니다.")

