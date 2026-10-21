"""GMS 임베딩으로 별도 Chroma 판례 색인을 구축한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient  # noqa: E402
from legal_rag.adapters.vector_store import ChromaCaseVectorStore  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.case_chunking import CaseChunk  # noqa: E402
from legal_rag.rag.indexing import index_chunks  # noqa: E402


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SafeLaw 판례 Chroma 색인 생성")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "processed" / "case_chunks.json")
    parser.add_argument("--persist-dir", type=Path, default=ROOT / "data" / "indexes" / "cases")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    api_key = os.getenv("GMS_KEY", "").strip()
    if not api_key:
        print("GMS_KEY 환경변수가 필요합니다.", file=sys.stderr)
        return 2
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    chunks = [CaseChunk(**{**item, "category": LegalCategory(item["category"]),
        "related_articles": tuple(item.get("related_articles", []))}) for item in payload]
    embedder = GmsEmbeddingClient(api_key,
        model_name=os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small"),
        base_url=os.getenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1"))
    store = ChromaCaseVectorStore(args.persist_dir, recreate=True)
    result = index_chunks(chunks, embedder, store, batch_size=args.batch_size)  # type: ignore[arg-type]
    print(f"{result.chunk_count}개 판례 청크를 {result.embedding_model} ({result.vector_dimension}차원)로 색인했습니다.")
    print(f"Chroma 판례 저장 건수: {store.count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
