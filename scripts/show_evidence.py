"""한 질문의 근거 목록을 Top-k별로 출력한다.

답변은 생성하지 않고 retrieve 노드와 같은 방식으로 근거 목록만 만든다. 판례 실시간
보강은 끈 상태로 실행해 Top-k 외의 요인으로 근거가 바뀌지 않게 한다.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.config import Settings  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.citations import CaseEvidence  # noqa: E402
from legal_rag.security.redaction import PrivacyGuard  # noqa: E402
from legal_rag.ui.streamlit_app import UiConfigurationError, build_pipeline  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings.from_environment()
    parser = argparse.ArgumentParser(description="SafeLaw Top-k별 근거 목록 비교")
    parser.add_argument("query", help="근거를 찾을 자연어 질문")
    parser.add_argument("--category", choices=[item.value for item in LegalCategory], required=True)
    parser.add_argument(
        "--top-k", type=int, nargs="+", default=[settings.rag_top_k],
        help="비교할 Top-k 값들. 기본값: .env의 RAG_TOP_K",
    )
    args = parser.parse_args()
    if any(value < 1 for value in args.top_k):
        parser.error("--top-k 값은 1 이상이어야 합니다.")

    try:
        pipeline = build_pipeline(replace(settings, law_api_oc=None))
    except UiConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    question = PrivacyGuard().redact(args.query).sanitized_text
    category = LegalCategory(args.category)
    for top_k in args.top_k:
        evidence = pipeline.retrieve_evidence(question, category=category, top_k=top_k)
        statutes = [item for item in evidence if not isinstance(item, CaseEvidence)]
        cases = [item for item in evidence if isinstance(item, CaseEvidence)]
        print(f"## Top-k {top_k}: 법령 {len(statutes)}건 · 판례 {len(cases)}건")
        for item in evidence:
            kind = "판례" if isinstance(item, CaseEvidence) else "법령"
            print(f"[근거 {item.citation_id}] {kind} · {item.label}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
