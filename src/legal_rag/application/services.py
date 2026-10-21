"""법률 질문 처리 유스케이스.

구체적인 RAG 구현은 후속 단계에서 연결한다. 이 모듈은 UI가
수집기나 Vector DB를 직접 호출하지 않게 막는 경계이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from legal_rag.domain.models import LegalCategory, LegalQuestion
from legal_rag.security.redaction import PrivacyGuard, RedactionResult


@dataclass(frozen=True, slots=True)
class PreparedQuestion:
    question: LegalQuestion
    privacy: RedactionResult


class PrepareLegalQuestion:
    def __init__(self, privacy_guard: PrivacyGuard | None = None) -> None:
        self._privacy_guard = privacy_guard or PrivacyGuard()

    def execute(
        self,
        *,
        category: LegalCategory,
        raw_text: str,
        extra_sensitive_terms: tuple[str, ...] = (),
    ) -> PreparedQuestion:
        privacy = self._privacy_guard.redact(raw_text, extra_sensitive_terms)
        return PreparedQuestion(
            question=LegalQuestion(category=category, sanitized_text=privacy.sanitized_text),
            privacy=privacy,
        )

