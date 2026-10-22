"""검색된 법령만 근거로 검증된 생활법률 안내를 생성한다."""

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
from legal_rag.config import Settings  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.pipeline import StatuteRagPipeline  # noqa: E402
from legal_rag.rag.retrieval import ExpandedStatuteRetriever, LegalQueryExpander  # noqa: E402
from legal_rag.security.redaction import PrivacyGuard  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SafeLaw 근거 제한 법령 안내 생성")
    parser.add_argument("query", help="답변할 자연어 질문")
    parser.add_argument("--category", choices=[item.value for item in LegalCategory], required=True)
    parser.add_argument("--top-k", type=int, default=Settings.from_environment().rag_top_k,
                        help="기본값: .env의 RAG_TOP_K")
    args = parser.parse_args()

    api_key = os.getenv("GMS_KEY", "").strip()
    if not api_key:
        print("GMS_KEY가 필요합니다.", file=sys.stderr)
        return 2

    privacy = PrivacyGuard().redact(args.query)
    base_url = os.getenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    query_llm = GmsChatClient(
        api_key,
        model_name=Settings.from_environment().query_model,
        base_url=base_url,
    )
    answer_llm = GmsChatClient(
        api_key,
        model_name=os.getenv("GMS_ANSWER_MODEL") or "gpt-5.4-mini",
        base_url=base_url,
    )
    retriever = ExpandedStatuteRetriever(
        GmsEmbeddingClient(
            api_key,
            model_name=os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small"),
            base_url=base_url,
        ),
        ChromaStatuteVectorStore(ROOT / "data" / "indexes" / "statutes"),
        LegalQueryExpander(query_llm),
    )
    answer = StatuteRagPipeline(retriever, answer_llm).answer(
        privacy.sanitized_text,
        category=LegalCategory(args.category),
        top_k=args.top_k,
    )

    print(f"개인정보 마스킹: {privacy.redaction_count}건")
    print(f"답변 상태: {answer.status.value}")
    print(answer.content)
    return 0 if answer.is_answered else 3


if __name__ == "__main__":
    raise SystemExit(main())
