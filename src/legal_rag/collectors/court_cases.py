"""국가법령정보센터가 제공하는 대법원 공개 판례 수집기."""

from __future__ import annotations

import html
import json
import re
import socket
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from legal_rag.domain.models import CaseDocument, LegalCategory, PrecedentLevel

JsonObject = dict[str, Any]
Transport = Callable[[str, float], bytes]


class CourtCaseApiError(RuntimeError):
    """판례 API 통신 또는 응답 규격 오류. 인증값은 메시지에 포함하지 않는다."""


@dataclass(frozen=True, slots=True)
class CaseSourceConfig:
    category: LegalCategory
    queries: tuple[str, ...]
    limit_per_query: int = 8

    @classmethod
    def from_dict(cls, value: JsonObject) -> "CaseSourceConfig":
        queries = tuple(str(item).strip() for item in value.get("queries", []) if str(item).strip())
        if not queries:
            raise ValueError("판례 검색어는 하나 이상이어야 합니다.")
        limit = int(value.get("limit_per_query", 8))
        if not 1 <= limit <= 100:
            raise ValueError("limit_per_query는 1~100이어야 합니다.")
        return cls(LegalCategory(value["category"]), queries, limit)


@dataclass(frozen=True, slots=True)
class CaseSearchResult:
    case_id: str
    case_number: str
    case_name: str
    court: str
    decision_date: date
    decision_type: str
    source_name: str


def _default_transport(url: str, timeout: float) -> bytes:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "SafeLaw/0.1 (SSAFY AI Core Project)"},
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _clean_html(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    raw = re.sub(r"\D", "", str(value or ""))
    if len(raw) != 8:
        raise CourtCaseApiError("판례 선고일자 형식이 올바르지 않습니다.")
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _split_numbered(value: str) -> tuple[str, ...]:
    cleaned = _clean_html(value)
    if not cleaned:
        return ()
    pieces = re.split(r"(?=\[[0-9]+\])", cleaned)
    return tuple(piece.strip() for piece in pieces if piece.strip())


def _split_references(value: str) -> tuple[str, ...]:
    cleaned = _clean_html(value)
    if not cleaned:
        return ()
    return tuple(dict.fromkeys(item.strip() for item in re.split(r"[;\n]", cleaned) if item.strip()))


def _extract_order(body: str) -> str:
    match = re.search(
        r"(?:^|\n)(?:【\s*)?주\s*문(?:\s*】)?\s*\n"
        r"(?P<order>.*?)(?=\n(?:【\s*)?(?:이\s*유|청구취지|상고이유|이유)(?:\s*】)?\s*(?:\n|$))",
        body,
        re.DOTALL,
    )
    return re.sub(r"\s+", " ", match.group("order")).strip() if match else ""


def classify_precedent(court: str, decision_type: str) -> PrecedentLevel:
    """공식 메타데이터만으로 판례의 권위 등급을 분류한다."""

    if "전원합의체" in decision_type:
        return PrecedentLevel.GRAND_BENCH
    if court.strip() == "대법원":
        return PrecedentLevel.SUPREME_COURT
    if "고등법원" in court or court.strip() == "특허법원":
        return PrecedentLevel.APPELLATE
    return PrecedentLevel.OTHER


def _most_specific_decision_type(detail_value: Any, search_value: str) -> str:
    detail_type = str(detail_value or "").strip()
    search_type = search_value.strip()
    if "전원합의체" in search_type and "전원합의체" not in detail_type:
        return search_type
    return detail_type or search_type


class CourtCaseOpenApiClient:
    SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
    SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"

    def __init__(self, oc: str, *, timeout: float = 20.0, max_retries: int = 3,
                 retry_delay: float = 0.5, transport: Transport | None = None) -> None:
        if not oc or not oc.strip():
            raise ValueError("LAW_API_OC가 필요합니다.")
        self._oc = oc.strip()
        self._timeout = timeout
        self._max_retries = max(1, max_retries)
        self._retry_delay = max(0.0, retry_delay)
        self._transport = transport or _default_transport

    def _request(self, endpoint: str, params: dict[str, str | int]) -> JsonObject:
        url = f"{endpoint}?{urlencode({**params, 'OC': self._oc, 'type': 'JSON'})}"
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                payload = json.loads(self._transport(url, self._timeout).decode("utf-8-sig"))
                if not isinstance(payload, dict):
                    raise CourtCaseApiError("판례 API 응답이 JSON 객체가 아닙니다.")
                if "result" in payload and "msg" in payload:
                    raise CourtCaseApiError("판례 API가 요청을 거부했습니다. 인증값과 요청 변수를 확인하세요.")
                return payload
            except CourtCaseApiError:
                raise
            except (HTTPError, URLError, TimeoutError, socket.timeout, UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * attempt)
        name = type(last_error).__name__ if last_error else "UnknownError"
        raise CourtCaseApiError(f"판례 API 요청에 실패했습니다({name}).") from last_error

    def search(self, query: str, *, display: int = 8, page: int = 1) -> list[CaseSearchResult]:
        payload = self._request(
            self.SEARCH_URL,
            {"target": "prec", "search": 2, "query": query, "display": display, "page": page},
        )
        root = payload.get("PrecSearch")
        if not isinstance(root, dict):
            raise CourtCaseApiError("판례 목록 응답에 'PrecSearch' 객체가 없습니다.")
        results: list[CaseSearchResult] = []
        for item in _as_list(root.get("prec")):
            if not isinstance(item, dict):
                continue
            case_id = str(item.get("판례일련번호", "")).strip()
            case_number = str(item.get("사건번호", "")).strip()
            decision_date = str(item.get("선고일자", "")).strip()
            if not case_id or not case_number or not decision_date:
                continue
            results.append(CaseSearchResult(
                case_id=case_id,
                case_number=case_number,
                case_name=str(item.get("사건명", "")).strip(),
                court=str(item.get("법원명", "")).strip(),
                decision_date=_parse_date(decision_date),
                decision_type=str(item.get("판결유형", "")).strip(),
                source_name=str(item.get("데이터출처명", "")).strip(),
            ))
        return results

    def fetch(self, case_id: str) -> JsonObject:
        payload = self._request(self.SERVICE_URL, {"target": "prec", "ID": case_id})
        root = payload.get("PrecService")
        if not isinstance(root, dict):
            raise CourtCaseApiError("판례 본문 응답에 'PrecService' 객체가 없습니다.")
        return root


def normalize_case(detail: JsonObject, category: LegalCategory,
                   search_result: CaseSearchResult | None = None) -> CaseDocument:
    case_id = str(detail.get("판례정보일련번호") or detail.get("판례일련번호") or "").strip()
    case_number = str(detail.get("사건번호") or (search_result.case_number if search_result else "")).strip()
    court = str(detail.get("법원명") or (search_result.court if search_result else "")).strip()
    case_name = str(detail.get("사건명") or (search_result.case_name if search_result else "")).strip()
    decision_type = _most_specific_decision_type(
        detail.get("판결유형"), search_result.decision_type if search_result else ""
    )
    body = _clean_html(detail.get("판례내용"))
    reasoning = _clean_html(detail.get("판결요지")) or body
    issues = _split_numbered(str(detail.get("판시사항", "")))
    order = _extract_order(body)
    announced = str(detail.get("선고", "")).strip()
    if announced == "선고":
        announced = ""
    result = order or decision_type or announced or "판결 결과 원문 확인 필요"
    raw_date: Any = detail.get("선고일자")
    if not raw_date and search_result:
        raw_date = search_result.decision_date
    if not case_id or not case_number or not court or not body:
        raise CourtCaseApiError("판례 본문에 필수 식별자·법원명·원문이 없습니다.")
    return CaseDocument(
        case_id=case_id,
        category=category,
        case_number=case_number,
        court=court,
        decision_date=_parse_date(raw_date),
        result=result,
        facts=body,
        reasoning=reasoning,
        source_url=f"https://www.law.go.kr/LSW/precInfoP.do?precSeq={case_id}",
        issues=issues,
        related_articles=_split_references(str(detail.get("참조조문", ""))),
        case_name=case_name,
        decision_type=decision_type,
        precedent_level=classify_precedent(court, decision_type),
    )


def collect_cases(client: CourtCaseOpenApiClient, configs: Iterable[CaseSourceConfig], *,
                  request_delay: float = 0.15) -> list[CaseDocument]:
    documents: list[CaseDocument] = []
    seen: set[str] = set()
    seen_case_numbers: set[str] = set()
    detail_cache: dict[str, JsonObject] = {}
    for config in configs:
        for query in config.queries:
            for result in client.search(query, display=config.limit_per_query):
                if result.source_name and result.source_name != "대법원":
                    continue
                scoped_id = f"{config.category.value}:{result.case_id}"
                if scoped_id in seen:
                    continue
                if result.case_id not in detail_cache:
                    detail_cache[result.case_id] = client.fetch(result.case_id)
                    if request_delay > 0:
                        time.sleep(request_delay)
                try:
                    document = normalize_case(detail_cache[result.case_id], config.category, result)
                except CourtCaseApiError:
                    continue
                search_text = " ".join((
                    *document.issues,
                    document.reasoning,
                    *document.related_articles,
                )).replace(" ", "")
                query_terms = [item for item in query.split() if len(item) >= 2]
                if query_terms and not all(item.replace(" ", "") in search_text for item in query_terms):
                    continue
                scoped_number = f"{config.category.value}:{document.case_number}"
                if scoped_number in seen_case_numbers:
                    continue
                documents.append(document)
                seen.add(scoped_id)
                seen_case_numbers.add(scoped_number)
    return documents

