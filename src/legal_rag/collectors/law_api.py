"""국가법령정보 공동활용 현행법령 API 수집기.

공식 API의 현행법령(시행일) 목록과 본문 JSON을 내부 모델로 변환한다.
인증값 ``OC``는 요청에만 사용하고 오류 메시지나 데이터셋에 기록하지 않는다.
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from legal_rag.domain.models import LegalCategory, StatuteDocument

JsonObject = dict[str, Any]
Transport = Callable[[str, float], bytes]


class LawApiError(RuntimeError):
    """API 통신 또는 응답 규격 오류. 인증값은 메시지에 포함하지 않는다."""


@dataclass(frozen=True, slots=True)
class LawSearchResult:
    law_name: str
    source_law_id: str
    law_sequence: str
    effective_date: date
    ministry: str
    law_type: str


@dataclass(frozen=True, slots=True)
class ArticleRange:
    start: int
    end: int

    def contains(self, article_number: int) -> bool:
        return self.start <= article_number <= self.end


@dataclass(frozen=True, slots=True)
class StatuteSourceConfig:
    law_name: str
    category: LegalCategory
    issue_tags: tuple[str, ...] = ()
    article_ranges: tuple[ArticleRange, ...] = ()

    def includes(self, article_number: int) -> bool:
        return not self.article_ranges or any(item.contains(article_number) for item in self.article_ranges)

    @classmethod
    def from_dict(cls, value: JsonObject) -> "StatuteSourceConfig":
        ranges = tuple(ArticleRange(int(item[0]), int(item[1])) for item in value.get("article_ranges", []))
        return cls(
            law_name=str(value["law_name"]),
            category=LegalCategory(value["category"]),
            issue_tags=tuple(str(item) for item in value.get("issue_tags", [])),
            article_ranges=ranges,
        )


def _default_transport(url: str, timeout: float) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "SafeLaw/0.1 (SSAFY AI Core Project)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _content(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("content", "")).strip()
    return str(value or "").strip()


def _parse_date(value: Any, field_name: str) -> date:
    raw = str(value or "").strip().replace("-", "")
    if len(raw) != 8 or not raw.isdigit():
        raise LawApiError(f"{field_name} 형식이 올바르지 않습니다.")
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _article_label(unit: JsonObject) -> str:
    number = str(unit.get("조문번호", "")).strip()
    branch = str(unit.get("조문가지번호", "") or "").strip()
    return f"제{number}조의{int(branch)}" if branch and branch.isdigit() and int(branch) else f"제{number}조"


def _flatten_article(unit: JsonObject) -> str:
    lines: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and (not lines or lines[-1] != text):
            lines.append(text)

    add(unit.get("조문내용"))
    for paragraph in _as_list(unit.get("항")):
        if not isinstance(paragraph, dict):
            continue
        add(paragraph.get("항내용"))
        for item in _as_list(paragraph.get("호")):
            if not isinstance(item, dict):
                continue
            add(item.get("호내용"))
            for subitem in _as_list(item.get("목")):
                if isinstance(subitem, dict):
                    add(subitem.get("목내용"))
    return "\n".join(lines)


class LawOpenApiClient:
    SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
    SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"

    def __init__(
        self,
        oc: str,
        *,
        timeout: float = 20.0,
        max_retries: int = 3,
        retry_delay: float = 0.5,
        transport: Transport | None = None,
    ) -> None:
        if not oc or not oc.strip():
            raise ValueError("LAW_API_OC가 필요합니다.")
        self._oc = oc.strip()
        self._timeout = timeout
        self._max_retries = max(1, max_retries)
        self._retry_delay = max(0.0, retry_delay)
        self._transport = transport or _default_transport

    def _request(self, endpoint: str, params: dict[str, str | int]) -> JsonObject:
        safe_params = {**params, "OC": self._oc, "type": "JSON"}
        url = f"{endpoint}?{urlencode(safe_params)}"
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                raw = self._transport(url, self._timeout)
                payload = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(payload, dict):
                    raise LawApiError("API 응답이 JSON 객체가 아닙니다.")
                return payload
            except (HTTPError, URLError, TimeoutError, socket.timeout, UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * attempt)
        error_name = type(last_error).__name__ if last_error else "UnknownError"
        raise LawApiError(f"국가법령정보 API 요청에 실패했습니다({error_name}).") from last_error

    def search_current_law(self, law_name: str) -> LawSearchResult:
        payload = self._request(
            self.SEARCH_URL,
            {
                "target": "eflaw",
                "search": 1,
                "query": law_name,
                "display": 100,
                "page": 1,
                "nw": 3,
            },
        )
        root = payload.get("LawSearch")
        if not isinstance(root, dict) or str(root.get("resultCode", "00")) != "00":
            raise LawApiError("현행법령 검색 응답이 성공 형식이 아닙니다.")
        candidates = [
            item for item in _as_list(root.get("law"))
            if isinstance(item, dict) and str(item.get("법령명한글", "")).strip() == law_name
        ]
        if not candidates:
            raise LawApiError(f"현행법령에서 '{law_name}'을(를) 찾지 못했습니다.")
        candidates.sort(key=lambda item: str(item.get("시행일자", "")), reverse=True)
        item = candidates[0]
        return LawSearchResult(
            law_name=law_name,
            source_law_id=str(item.get("법령ID", "")).strip(),
            law_sequence=str(item.get("법령일련번호", "")).strip(),
            effective_date=_parse_date(item.get("시행일자"), "시행일자"),
            ministry=str(item.get("소관부처명", "")).strip(),
            law_type=str(item.get("법령구분명", "")).strip(),
        )

    def fetch_current_law(self, source_law_id: str) -> JsonObject:
        payload = self._request(
            self.SERVICE_URL,
            {"target": "eflaw", "ID": source_law_id},
        )
        law = payload.get("법령")
        if not isinstance(law, dict):
            raise LawApiError("법령 본문 응답에 '법령' 객체가 없습니다.")
        return law


def normalize_statutes(
    law: JsonObject,
    config: StatuteSourceConfig,
    search_result: LawSearchResult | None = None,
) -> list[StatuteDocument]:
    basic = law.get("기본정보")
    articles = law.get("조문")
    if not isinstance(basic, dict) or not isinstance(articles, dict):
        raise LawApiError("법령 본문에 기본정보 또는 조문이 없습니다.")

    law_name = str(basic.get("법령명_한글", "")).strip()
    if law_name != config.law_name:
        raise LawApiError(f"요청한 법령과 응답 법령명이 다릅니다: {config.law_name} != {law_name}")

    source_law_id = str(basic.get("법령ID", "")).strip()
    law_sequence = search_result.law_sequence if search_result else ""
    law_key = str(law.get("법령키", "")).strip()
    effective_date = _parse_date(basic.get("시행일자"), "시행일자")
    promulgation_date = _parse_date(basic.get("공포일자"), "공포일자")
    ministry = _content(basic.get("소관부처"))
    law_type = _content(basic.get("법종구분"))

    documents: list[StatuteDocument] = []
    for unit in _as_list(articles.get("조문단위")):
        if not isinstance(unit, dict) or unit.get("조문여부") != "조문":
            continue
        number_raw = str(unit.get("조문번호", "")).strip()
        if not number_raw.isdigit() or not config.includes(int(number_raw)):
            continue
        text = _flatten_article(unit)
        if not text:
            continue
        article_no = _article_label(unit)
        article_key = str(unit.get("조문키", "")).strip()
        title = str(unit.get("조문제목", "")).strip() or "제목 없음"
        public_url = f"https://www.law.go.kr/법령/{quote(law_name, safe='')}/{quote(article_no, safe='')}"
        documents.append(
            StatuteDocument(
                law_id=f"{source_law_id}:{article_key or article_no}",
                category=config.category,
                law_name=law_name,
                article_no=article_no,
                article_title=title,
                text=text,
                effective_date=_parse_date(unit.get("조문시행일자") or basic.get("시행일자"), "조문시행일자"),
                source_url=public_url,
                issue_tags=config.issue_tags,
                source_law_id=source_law_id,
                law_sequence=law_sequence,
                law_key=law_key,
                article_key=article_key,
                ministry=ministry,
                law_type=law_type,
                promulgation_date=promulgation_date,
            )
        )
    return documents


def collect_statutes(
    client: LawOpenApiClient,
    configs: Iterable[StatuteSourceConfig],
    *,
    request_delay: float = 0.2,
) -> list[StatuteDocument]:
    body_cache: dict[str, tuple[JsonObject, LawSearchResult]] = {}
    documents: list[StatuteDocument] = []
    seen_ids: set[str] = set()
    for config in configs:
        if config.law_name not in body_cache:
            result = client.search_current_law(config.law_name)
            body_cache[config.law_name] = (
                client.fetch_current_law(result.source_law_id),
                result,
            )
            if request_delay > 0:
                time.sleep(request_delay)
        law, result = body_cache[config.law_name]
        for document in normalize_statutes(law, config, result):
            scoped_id = f"{document.category.value}:{document.law_id}"
            if scoped_id not in seen_ids:
                documents.append(document)
                seen_ids.add(scoped_id)
    return documents

