"""LLM 호출 전에 실행하는 로컬 개인정보 마스킹.

이 모듈은 외부 API를 호출하지 않는다. 매핑은 호출자의 메모리에만
반환하며, 원문을 포함하는 repr로 로그에 노출하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Pattern


@dataclass(frozen=True, slots=True)
class RedactedEntity:
    kind: str
    placeholder: str
    original: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class RedactionResult:
    sanitized_text: str
    entities: tuple[RedactedEntity, ...] = field(default_factory=tuple, repr=False)

    @property
    def redaction_count(self) -> int:
        return len(self.entities)

    @property
    def is_redacted(self) -> bool:
        return bool(self.entities)

    def __repr__(self) -> str:
        return (
            "RedactionResult("
            f"sanitized_text={self.sanitized_text!r}, "
            f"redaction_count={self.redaction_count})"
        )


@dataclass(frozen=True, slots=True)
class _Rule:
    kind: str
    pattern: Pattern[str]


class PrivacyGuard:
    """보수적인 규칙 기반 마스킹.

    자유 형식의 인명·회사명은 규칙만으로 완전히 판별할 수 없으므로,
    UI에서 별도로 받은 민감 단어를 extra_terms로 전달할 수 있다.
    """

    _RULES = (
        _Rule("RRN", re.compile(r"(?<!\d)\d{6}\s*[- ]?\s*[1-8]\d{6}(?!\d)")),
        _Rule("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
        _Rule("PHONE", re.compile(r"(?<!\d)(?:01[016789]|02|0[3-6][1-5])[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")),
        _Rule("CARD", re.compile(r"(?<!\d)(?:\d{4}[- ]?){3}\d{4}(?!\d)")),
        _Rule("ACCOUNT", re.compile(r"(?<!\d)\d{2,6}[- ]\d{2,6}[- ]\d{2,8}(?!\d)")),
        _Rule(
            "ADDRESS",
            re.compile(
                r"(?:서울(?:특별시)?|부산(?:광역시)?|대구(?:광역시)?|인천(?:광역시)?|"
                r"광주(?:광역시)?|대전(?:광역시)?|울산(?:광역시)?|세종(?:특별자치시)?|"
                r"경기도|강원(?:특별자치도)?|충청[남북]도|전북특별자치도|전라[남북]도|"
                r"경상[남북]도|제주특별자치도)\s+"
                r"[\w가-힣·.-]+(?:시|군|구)\s+[\w가-힣·.-]+(?:로|길|동|읍|면)"
                r"(?:\s+\d+(?:-\d+)?)?"
            ),
        ),
        _Rule(
            "PERSON",
            re.compile(r"(?:(?:이름|성명|임대인|임차인|피상속인|근로자|사용자)\s*[:은는이가]?\s*)([가-힣]{2,4})"),
        ),
        _Rule(
            "COMPANY",
            re.compile(r"(?:(?:회사명|사업장|근무지)\s*[:은는이가]?\s*)([A-Za-z가-힣0-9&.㈜()]{2,30})"),
        ),
    )

    def redact(self, text: str, extra_terms: Iterable[str] = ()) -> RedactionResult:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("마스킹할 문자열이 필요합니다.")

        sanitized = text
        entities: list[RedactedEntity] = []
        counters: dict[str, int] = {}
        known: dict[tuple[str, str], str] = {}

        def placeholder_for(kind: str, original: str) -> str:
            key = (kind, original)
            if key in known:
                return known[key]
            counters[kind] = counters.get(kind, 0) + 1
            placeholder = f"[{kind}_{counters[kind]}]"
            known[key] = placeholder
            entities.append(RedactedEntity(kind=kind, placeholder=placeholder, original=original))
            return placeholder

        for rule in self._RULES:
            def replace(match: re.Match[str], *, current_rule: _Rule = rule) -> str:
                original = match.group(0)
                sensitive = match.group(1) if match.lastindex else original
                placeholder = placeholder_for(current_rule.kind, sensitive)
                if match.lastindex:
                    return original.replace(sensitive, placeholder, 1)
                return placeholder

            sanitized = rule.pattern.sub(replace, sanitized)

        terms = sorted({term.strip() for term in extra_terms if term and term.strip()}, key=len, reverse=True)
        for term in terms:
            placeholder = placeholder_for("CUSTOM", term)
            sanitized = sanitized.replace(term, placeholder)

        return RedactionResult(sanitized_text=sanitized, entities=tuple(entities))

