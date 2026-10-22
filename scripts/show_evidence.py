"""한 질문의 근거 목록을 Top-k별 또는 검색 방식별로 출력한다.

답변은 생성하지 않고 retrieve 노드와 같은 방식으로 근거 목록만 만든다. 판례 실시간
보강은 끈 상태로 실행해 비교 대상 외의 요인으로 근거가 바뀌지 않게 한다.
`--compare-search`는 검색어 변환을 한 번만 실행해 같은 검색 계획으로 유사도 검색과
MMR을 비교한다.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.config import Settings  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.citations import CaseEvidence, LegalEvidence  # noqa: E402
from legal_rag.rag.pipeline import evidence_from_retrieval  # noqa: E402
from legal_rag.security.redaction import PrivacyGuard  # noqa: E402
from legal_rag.ui.streamlit_app import UiConfigurationError, build_pipeline  # noqa: E402


def print_evidence(title: str, evidence: Sequence[LegalEvidence]) -> None:
    statutes = [item for item in evidence if not isinstance(item, CaseEvidence)]
    cases = [item for item in evidence if isinstance(item, CaseEvidence)]
    print(f"## {title}: 법령 {len(statutes)}건 · 판례 {len(cases)}건")
    for item in evidence:
        kind = "판례" if isinstance(item, CaseEvidence) else "법령"
        print(f"[근거 {item.citation_id}] {kind} · {item.label}")
    print()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = replace(Settings.from_environment(), law_api_oc=None)
    parser = argparse.ArgumentParser(description="SafeLaw 근거 목록 비교")
    parser.add_argument("query", help="근거를 찾을 자연어 질문")
    parser.add_argument("--category", choices=[item.value for item in LegalCategory], required=True)
    parser.add_argument(
        "--top-k", type=int, nargs="+", default=[settings.rag_top_k],
        help="비교할 Top-k 값들. 기본값: .env의 RAG_TOP_K",
    )
    parser.add_argument(
        "--compare-search", action="store_true",
        help="같은 검색 계획으로 유사도 검색과 MMR 근거 목록을 나란히 출력",
    )
    args = parser.parse_args()
    if any(value < 1 for value in args.top_k):
        parser.error("--top-k 값은 1 이상이어야 합니다.")

    question = PrivacyGuard().redact(args.query).sanitized_text
    category = LegalCategory(args.category)
    try:
        if not args.compare_search:
            pipeline = build_pipeline(settings)
            for top_k in args.top_k:
                evidence = pipeline.retrieve_evidence(question, category=category, top_k=top_k)
                print_evidence(f"{settings.rag_search_mode} · Top-k {top_k}", evidence)
            return 0

        retrievers = {
            mode: build_pipeline(replace(settings, rag_search_mode=mode)).retriever
            for mode in ("similarity", "mmr")
        }
    except UiConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    plan = retrievers["similarity"].plan(question, category)  # type: ignore[attr-defined]
    print(f"법률 검색어: {', '.join(plan.legal_terms) or '없음'}")
    print(f"MMR 후보 풀 {settings.rag_mmr_fetch_k}건 · lambda {settings.rag_mmr_lambda}\n")
    for top_k in args.top_k:
        for mode, retriever in retrievers.items():
            retrieval = retriever.retrieve_with_plan(plan, category=category, top_k=top_k)  # type: ignore[attr-defined]
            print_evidence(f"{mode} · Top-k {top_k}", evidence_from_retrieval(retrieval)[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
