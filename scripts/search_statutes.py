"""자연어 질문을 확장하여 Chroma 법령 색인을 검색한다."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient  # noqa: E402
from legal_rag.adapters.gms_llm import GmsChatClient  # noqa: E402
from legal_rag.adapters.vector_store import ChromaStatuteVectorStore  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.retrieval import ExpandedStatuteRetriever, LegalQueryExpander  # noqa: E402
from legal_rag.security.redaction import PrivacyGuard  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SafeLaw 법령 의미 검색")
    parser.add_argument("query", help="검색할 자연어 질문")
    parser.add_argument("--category", choices=[item.value for item in LegalCategory], required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    api_key = os.getenv("GMS_KEY", "").strip()
    if not api_key:
        print("GMS_KEY가 필요합니다.", file=sys.stderr)
        return 2

    sanitized = PrivacyGuard().redact(args.query).sanitized_text
    base_url = os.getenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    embedder = GmsEmbeddingClient(
        api_key,
        model_name=os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small"),
        base_url=base_url,
    )
    llm = GmsChatClient(
        api_key,
        model_name=os.getenv("GMS_CHAT_MODEL", "gpt-5-nano"),
        base_url=base_url,
    )
    store = ChromaStatuteVectorStore(ROOT / "data" / "indexes" / "statutes")
    retriever = ExpandedStatuteRetriever(embedder, store, LegalQueryExpander(llm))
    result = retriever.retrieve(
        sanitized,
        category=LegalCategory(args.category),
        top_k=args.top_k,
    )

    print(f"마스킹된 질문: {result.plan.original_query}")
    print(f"재작성 질의: {result.plan.rewritten_query}")
    print(f"법률 용어: {', '.join(result.plan.legal_terms) or '없음'}")
    print(f"LLM 확장 사용: {result.plan.used_llm}")
    print("검색 결과:")
    for rank, hit in enumerate(result.hits, start=1):
        metadata = hit.metadata
        print(
            f"{rank}. {metadata['law_name']} {metadata['article_no']} "
            f"{metadata['article_title']} | score={hit.score:.6f} "
            f"distance={hit.distance:.6f}"
        )
        print(f"   {metadata['source_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
