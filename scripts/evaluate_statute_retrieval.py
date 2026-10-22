"""고정 평가셋으로 법령 검색 Recall@5와 MRR을 측정한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient  # noqa: E402
from legal_rag.adapters.gms_llm import GmsChatClient  # noqa: E402
from legal_rag.adapters.vector_store import ChromaStatuteVectorStore  # noqa: E402
from legal_rag.config import Settings  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.retrieval import ExpandedStatuteRetriever, LegalQueryExpander  # noqa: E402
from legal_rag.security.redaction import PrivacyGuard  # noqa: E402

EVALUATOR_VERSION = "4"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def expected_key(item: dict[str, str]) -> tuple[str, str]:
    return item["law_name"], item["article_no"]


def evaluate_case(case: dict[str, Any], retriever: ExpandedStatuteRetriever, top_k: int) -> dict[str, Any]:
    sanitized = PrivacyGuard().redact(case["query"]).sanitized_text
    result = retriever.retrieve(
        sanitized,
        category=LegalCategory(case["category"]),
        top_k=top_k,
    )
    expected = {expected_key(item) for item in case["expected"]}
    retrieved = [
        (str(hit.metadata.get("law_name", "")), str(hit.metadata.get("article_no", "")))
        for hit in result.hits
    ]
    relevant_ranks = [rank for rank, item in enumerate(retrieved, start=1) if item in expected]
    found = {item for item in retrieved if item in expected}
    recall = len(found) / len(expected)
    reciprocal_rank = 1 / relevant_ranks[0] if relevant_ranks else 0.0
    return {
        "id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "expected": case["expected"],
        "rewritten_query": result.plan.rewritten_query,
        "legal_terms": list(result.plan.legal_terms),
        "used_llm": result.plan.used_llm,
        "top_k": [
            {
                "rank": rank,
                "law_name": hit.metadata.get("law_name"),
                "article_no": hit.metadata.get("article_no"),
                "article_title": hit.metadata.get("article_title"),
                "score": round(hit.score, 8),
                "distance": round(hit.distance, 8),
                "source_url": hit.metadata.get("source_url"),
            }
            for rank, hit in enumerate(result.hits, start=1)
        ],
        "relevant_ranks": relevant_ranks,
        "recall_at_5": recall,
        "reciprocal_rank": reciprocal_rank,
        "hit_at_5": bool(relevant_ranks),
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        groups[result["category"]].append(result)
    groups["overall"] = results
    metrics: dict[str, Any] = {}
    for name, items in groups.items():
        count = len(items)
        metrics[name] = {
            "case_count": count,
            "recall_at_5": sum(item["recall_at_5"] for item in items) / count,
            "mrr": sum(item["reciprocal_rank"] for item in items) / count,
            "hit_at_5": sum(item["hit_at_5"] for item in items) / count,
        }
    return metrics


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SafeLaw 법령 검색 품질 평가")
    parser.add_argument("--cases", type=Path, default=ROOT / "data" / "evaluation" / "statute_retrieval_cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "evaluation" / "statute_retrieval_results.json")
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("GMS_KEY", "").strip()
    if not api_key:
        print("GMS_KEY가 필요합니다.", file=sys.stderr)
        return 2
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if len(cases) < 30:
        raise ValueError("평가 질문은 총 30건 이상이어야 합니다.")
    counts: dict[str, int] = defaultdict(int)
    for case in cases:
        counts[case["category"]] += 1
    if any(counts[category.value] < 10 for category in LegalCategory):
        raise ValueError("각 도메인별 평가 질문이 10건 이상이어야 합니다.")

    base_url = os.getenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    embedding_model = os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small")
    chat_model = Settings.from_environment().query_model
    embedder = GmsEmbeddingClient(api_key, model_name=embedding_model, base_url=base_url)
    llm = GmsChatClient(api_key, model_name=chat_model, base_url=base_url)
    store = ChromaStatuteVectorStore(ROOT / "data" / "indexes" / "statutes")
    retriever = ExpandedStatuteRetriever(embedder, store, LegalQueryExpander(llm))

    saved: dict[str, dict[str, Any]] = {}
    if args.output.exists() and not args.no_resume:
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if previous.get("evaluator_version") == EVALUATOR_VERSION:
            saved = {item["id"]: item for item in previous.get("results", [])}

    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        cached = saved.get(case["id"])
        if cached and cached.get("query") == case["query"] and cached.get("expected") == case["expected"]:
            result = cached
            state = "재사용"
        else:
            result = evaluate_case(case, retriever, top_k=5)
            state = "완료"
            if args.delay > 0:
                time.sleep(args.delay)
        results.append(result)
        report = {
            "evaluator_version": EVALUATOR_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "embedding_model": embedding_model,
            "chat_model": chat_model,
            "case_file": args.cases.relative_to(ROOT).as_posix(),
            "metrics": aggregate(results),
            "results": results,
        }
        write_json(args.output, report)
        first_rank = result["relevant_ranks"][0] if result["relevant_ranks"] else "실패"
        print(f"[{index:02d}/{len(cases)}] {case['id']} {state} | 첫 정답 순위: {first_rank}")

    metrics = aggregate(results)
    print("\n평가 완료")
    for category, values in metrics.items():
        print(
            f"{category}: Recall@5={values['recall_at_5']:.3f}, "
            f"MRR={values['mrr']:.3f}, Hit@5={values['hit_at_5']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
