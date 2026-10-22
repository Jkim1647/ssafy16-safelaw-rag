"""고정 30문항으로 검색-생성-인용검증-거부 전체 파이프라인을 평가한다."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient  # noqa: E402
from legal_rag.adapters.gms_llm import GmsChatClient  # noqa: E402
from legal_rag.adapters.vector_store import ChromaCaseVectorStore, ChromaStatuteVectorStore  # noqa: E402
from legal_rag.config import Settings  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.citations import CaseEvidence  # noqa: E402
from legal_rag.rag.pipeline import AnswerStatus, GroundedAnswer, StatuteRagPipeline  # noqa: E402
from legal_rag.rag.retrieval import CombinedLegalRetriever, ExpandedStatuteRetriever, LegalQueryExpander  # noqa: E402
from legal_rag.security.redaction import PrivacyGuard  # noqa: E402

EVALUATOR_VERSION = "1"
CORRECT_REFUSAL_STATUSES = {AnswerStatus.NO_EVIDENCE.value, AnswerStatus.INSUFFICIENT_EVIDENCE.value}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "law.go.kr" or host.endswith(".law.go.kr"))


def audit_rendered_answer(answer: GroundedAnswer) -> dict[str, Any]:
    """렌더링된 주장마다 실제 sources의 근거 번호가 붙었는지 독립 검사한다."""
    if not answer.is_answered:
        return {"claim_count": 0, "grounded_claim_count": 0, "ungrounded_claim_count": 0,
                "citation_valid": True, "official_sources": True}
    source_ids = {item.citation_id for item in answer.sources}
    official = bool(answer.sources) and all(_official_url(item.source_url) for item in answer.sources)
    body = answer.content.split("### 확인된 근거", 1)[0]
    claims: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(">"):
            continue
        claims.append(stripped[2:].strip() if stripped.startswith("- ") else stripped)
    grounded = 0
    for claim in claims:
        ids = {int(value) for value in re.findall(r"\[근거\s+(\d+)\]", claim)}
        if ids and ids.issubset(source_ids):
            grounded += 1
    return {
        "claim_count": len(claims),
        "grounded_claim_count": grounded,
        "ungrounded_claim_count": len(claims) - grounded,
        "citation_valid": bool(claims) and grounded == len(claims) and official,
        "official_sources": official,
    }


def evaluate_item(item: dict[str, Any], pipeline: StatuteRagPipeline) -> dict[str, Any]:
    privacy = PrivacyGuard().redact(item["query"])
    answer = pipeline.answer(
        privacy.sanitized_text,
        category=LegalCategory(item["category"]),
        top_k=5,
    )
    audit = audit_rendered_answer(answer)
    expected_answerable = bool(item["expected_answerable"])
    expected_cases = set(item.get("expected_case_numbers", []))
    cited_cases = {
        source.case_number for source in answer.sources if isinstance(source, CaseEvidence)
    }
    correct_refusal = (
        not expected_answerable and answer.status.value in CORRECT_REFUSAL_STATUSES
    )
    safely_grounded_or_blocked = (
        (answer.is_answered and audit["ungrounded_claim_count"] == 0)
        or (not answer.is_answered)
    )
    return {
        "id": item["id"], "category": item["category"], "query": item["query"],
        "expected_answerable": expected_answerable,
        "expected_case_numbers": item.get("expected_case_numbers", []),
        "status": answer.status.value,
        "answered": answer.is_answered,
        "correct_answer_behavior": answer.is_answered == expected_answerable,
        "correct_refusal": correct_refusal,
        "citation_audit": audit,
        "safe_grounding_behavior": safely_grounded_or_blocked,
        "expected_case_cited": bool(expected_cases.intersection(cited_cases)) if expected_cases else None,
        "cited_case_numbers": sorted(cited_cases),
        "sources": [{
            "citation_id": source.citation_id,
            "type": "court_case" if isinstance(source, CaseEvidence) else "statute",
            "label": source.label,
            "source_url": source.source_url,
        } for source in answer.sources],
        "retrieved_evidence_count": answer.retrieved_count,
        "generation_attempts": answer.generation_attempts,
        "validation_failures": answer.validation_failures,
        "content": answer.content,
        "redaction_count": privacy.redaction_count,
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [x for x in results if x["expected_answerable"]]
    negatives = [x for x in results if not x["expected_answerable"]]
    answered = [x for x in results if x["answered"]]
    answered_positives = [x for x in positives if x["answered"]]
    expected_case_items = [x for x in answered_positives if x["expected_case_cited"] is not None]
    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None
    return {
        "question_count": len(results),
        "answerable_count": len(positives),
        "refusal_probe_count": len(negatives),
        "answer_success_rate": ratio(sum(x["answered"] for x in positives), len(positives)),
        "citation_accuracy": ratio(
            sum(x["citation_audit"]["citation_valid"] for x in answered), len(answered)
        ),
        "ungrounded_claim_block_rate": ratio(
            sum(x["safe_grounding_behavior"] for x in results), len(results)
        ),
        "refusal_accuracy": ratio(sum(x["correct_refusal"] for x in negatives), len(negatives)),
        "false_refusal_rate": ratio(sum(not x["answered"] for x in positives), len(positives)),
        "expected_case_citation_rate": ratio(
            sum(bool(x["expected_case_cited"]) for x in expected_case_items), len(expected_case_items)
        ),
        "generation_or_validation_failure_count": sum(
            x["status"] in {AnswerStatus.INVALID_CITATIONS.value, AnswerStatus.GENERATION_FAILED.value}
            for x in results
        ),
        "validation_failure_attempt_count": sum(x.get("validation_failures", 0) for x in results),
        "status_counts": dict(sorted(__import__("collections").Counter(x["status"] for x in results).items())),
    }


def build_pipeline(api_key: str, base_url: str, embedding_model: str,
                   query_model: str, answer_model: str) -> StatuteRagPipeline:
    embedder = GmsEmbeddingClient(api_key, model_name=embedding_model, base_url=base_url)
    query_llm = GmsChatClient(api_key, model_name=query_model, base_url=base_url)
    statutes = ExpandedStatuteRetriever(
        embedder, ChromaStatuteVectorStore(ROOT / "data/indexes/statutes"), LegalQueryExpander(query_llm)
    )
    cases = ExpandedStatuteRetriever(
        embedder, ChromaCaseVectorStore(ROOT / "data/indexes/cases"), LegalQueryExpander(query_llm),
        candidate_pool_factor=10, deduplicate_metadata_key="case_number",
    )
    return StatuteRagPipeline(
        CombinedLegalRetriever(statutes, cases),
        GmsChatClient(api_key, model_name=answer_model, base_url=base_url),
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SafeLaw End-to-End RAG 평가")
    parser.add_argument("--cases", type=Path, default=ROOT / "data/evaluation/end_to_end_cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/evaluation/end_to_end_results.json")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--ids", help="쉼표로 구분한 평가 문항 ID만 실행")
    args = parser.parse_args()
    api_key = os.getenv("GMS_KEY", "").strip()
    if not api_key:
        print("GMS_KEY가 필요합니다.", file=sys.stderr); return 2
    items = json.loads(args.cases.read_text(encoding="utf-8"))
    counts = defaultdict(int)
    refusal_counts = defaultdict(int)
    for item in items:
        counts[item["category"]] += 1
        if not item["expected_answerable"]: refusal_counts[item["category"]] += 1
    if len(items) != 30 or any(counts[x.value] != 10 for x in LegalCategory):
        raise ValueError("E2E 평가셋은 도메인별 10건, 총 30건이어야 합니다.")
    if any(refusal_counts[x.value] != 2 for x in LegalCategory):
        raise ValueError("각 도메인에는 거부 문항이 정확히 2건이어야 합니다.")
    if args.ids:
        selected = {value.strip() for value in args.ids.split(",") if value.strip()}
        items = [item for item in items if item["id"] in selected]
        if len(items) != len(selected):
            raise ValueError("존재하지 않는 평가 문항 ID가 있습니다.")
    base_url = os.getenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    embedding_model = os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small")
    query_model = Settings.from_environment().query_model
    answer_model = os.getenv("GMS_ANSWER_MODEL") or "gpt-5.4-mini"
    pipeline = build_pipeline(api_key, base_url, embedding_model, query_model, answer_model)
    saved = {}
    if args.output.exists() and not args.no_resume:
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if previous.get("evaluator_version") == EVALUATOR_VERSION:
            saved = {x["id"]: x for x in previous.get("results", [])}
    results = []
    for index, item in enumerate(items, 1):
        result = saved.get(item["id"])
        if not result or result.get("query") != item["query"]:
            result = evaluate_item(item, pipeline)
        results.append(result)
        report = {
            "evaluator_version": EVALUATOR_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "review_status": "개발자 라벨링·법률 전문가 미검수",
            "embedding_model": embedding_model, "query_model": query_model,
            "answer_model": answer_model,
            "metrics": aggregate(results), "results": results,
        }
        write_json(args.output, report)
        print(f"[{index:02d}/{len(items)}] {item['id']} | expected={item['expected_answerable']} status={result['status']}")
    print(json.dumps(aggregate(results), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
