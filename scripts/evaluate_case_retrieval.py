"""판례를 사건번호 단위로 중복 제거해 Recall@5, MRR, 오염률을 측정한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient  # noqa: E402
from legal_rag.adapters.gms_llm import GmsChatClient  # noqa: E402
from legal_rag.adapters.vector_store import ChromaCaseVectorStore  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.retrieval import ExpandedStatuteRetriever, LegalQueryExpander  # noqa: E402
from legal_rag.security.redaction import PrivacyGuard  # noqa: E402

EVALUATOR_VERSION = "1"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def unique_case_hits(hits: tuple[Any, ...], top_k: int) -> list[Any]:
    result, seen = [], set()
    for hit in hits:
        number = str(hit.metadata.get("case_number", ""))
        key = number or hit.chunk_id
        if key in seen:
            continue
        seen.add(key)
        result.append(hit)
        if len(result) == top_k:
            break
    return result


def evaluate_case(case: dict[str, Any], retriever: ExpandedStatuteRetriever,
                  top_k: int = 5) -> dict[str, Any]:
    query = PrivacyGuard().redact(case["query"]).sanitized_text
    retrieval = retriever.retrieve(query, category=LegalCategory(case["category"]),
                                   top_k=max(top_k * 4, 20))
    hits = unique_case_hits(retrieval.hits, top_k)
    expected = set(case["expected_case_numbers"])
    relevant = expected | set(case.get("acceptable_case_numbers", []))
    numbers = [str(hit.metadata.get("case_number", "")) for hit in hits]
    ranks = [rank for rank, number in enumerate(numbers, 1) if number in expected]
    found = expected.intersection(numbers)
    irrelevant = sum(number not in relevant for number in numbers)
    denominator = len(numbers) or top_k
    return {
        "id": case["id"], "category": case["category"], "query": case["query"],
        "expected_case_numbers": case["expected_case_numbers"],
        "acceptable_case_numbers": case.get("acceptable_case_numbers", []),
        "rewritten_query": retrieval.plan.rewritten_query,
        "legal_terms": list(retrieval.plan.legal_terms),
        "top_k": [{
            "rank": rank, "case_number": hit.metadata.get("case_number"),
            "case_name": hit.metadata.get("case_name"), "court": hit.metadata.get("court"),
            "section": hit.metadata.get("section"), "score": round(hit.score, 8),
            "source_url": hit.metadata.get("source_url"),
        } for rank, hit in enumerate(hits, 1)],
        "relevant_ranks": ranks,
        "recall_at_5": len(found) / len(expected),
        "reciprocal_rank": 1 / ranks[0] if ranks else 0.0,
        "hit_at_5": bool(ranks),
        "contamination_at_5": irrelevant / denominator,
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        groups[result["category"]].append(result)
    groups["overall"] = results
    metrics = {}
    for name, items in groups.items():
        count = len(items)
        metrics[name] = {
            "case_count": count,
            "recall_at_5": sum(x["recall_at_5"] for x in items) / count,
            "mrr": sum(x["reciprocal_rank"] for x in items) / count,
            "hit_at_5": sum(x["hit_at_5"] for x in items) / count,
            "contamination_at_5": sum(x["contamination_at_5"] for x in items) / count,
        }
    return metrics


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SafeLaw 판례 검색 평가")
    parser.add_argument("--cases", type=Path, default=ROOT / "data/evaluation/case_retrieval_cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/evaluation/case_retrieval_results.json")
    parser.add_argument("--scope", default="현재 Chroma 판례 색인")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    api_key = os.getenv("GMS_KEY", "").strip()
    if not api_key:
        print("GMS_KEY가 필요합니다.", file=sys.stderr)
        return 2
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    counts = defaultdict(int)
    for case in cases:
        counts[case["category"]] += 1
    if len(cases) != 30 or any(counts[x.value] != 10 for x in LegalCategory):
        raise ValueError("평가셋은 도메인별 10건, 총 30건이어야 합니다.")
    base_url = os.getenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    embedding_model = os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small")
    chat_model = os.getenv("GMS_QUERY_MODEL") or os.getenv("GMS_CHAT_MODEL", "gpt-5-nano")
    retriever = ExpandedStatuteRetriever(
        GmsEmbeddingClient(api_key, model_name=embedding_model, base_url=base_url),
        ChromaCaseVectorStore(ROOT / "data/indexes/cases"),
        LegalQueryExpander(GmsChatClient(api_key, model_name=chat_model, base_url=base_url)),
    )
    saved = {}
    if args.output.exists() and not args.no_resume:
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if previous.get("evaluator_version") == EVALUATOR_VERSION:
            saved = {x["id"]: x for x in previous.get("results", [])}
    results = []
    for index, case in enumerate(cases, 1):
        result = saved.get(case["id"])
        if not result or result.get("query") != case["query"]:
            result = evaluate_case(case, retriever)
        results.append(result)
        report = {
            "evaluator_version": EVALUATOR_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "review_status": "개발자 라벨링·법률 전문가 미검수",
            "embedding_model": embedding_model, "chat_model": chat_model,
            "dataset_scope": args.scope,
            "metrics": aggregate(results), "results": results,
        }
        write_json(args.output, report)
        first = result["relevant_ranks"][0] if result["relevant_ranks"] else "실패"
        print(f"[{index:02d}/30] {case['id']} | 첫 정답 순위: {first}")
    print(json.dumps(aggregate(results)["overall"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
