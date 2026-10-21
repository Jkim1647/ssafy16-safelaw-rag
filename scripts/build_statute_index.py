"""GMS 임베딩을 생성하여 Chroma 법령 색인을 구축한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient  # noqa: E402
from legal_rag.adapters.vector_store import ChromaStatuteVectorStore  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.chunking import StatuteChunk  # noqa: E402
from legal_rag.rag.indexing import index_chunks  # noqa: E402


def load_chunks(path: Path) -> list[StatuteChunk]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        StatuteChunk(
            **{
                **item,
                "category": LegalCategory(item["category"]),
                "issue_tags": tuple(item.get("issue_tags", [])),
            }
        )
        for item in payload
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="SafeLaw 법령 Chroma 색인 생성")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "processed" / "statute_chunks.json")
    parser.add_argument("--persist-dir", type=Path, default=ROOT / "data" / "indexes" / "statutes")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    api_key = os.getenv("GMS_KEY", "").strip()
    if not api_key:
        print("GMS_KEY 환경변수가 필요합니다.", file=sys.stderr)
        return 2

    embedder = GmsEmbeddingClient(
        api_key,
        model_name=os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small"),
        base_url=os.getenv(
            "GMS_BASE_URL",
            "https://gms.ssafy.io/gmsapi/api.openai.com/v1",
        ),
    )
    store = ChromaStatuteVectorStore(args.persist_dir, recreate=True)
    result = index_chunks(load_chunks(args.input), embedder, store, batch_size=args.batch_size)
    print(
        f"{result.chunk_count}개 청크를 {result.embedding_model} "
        f"({result.vector_dimension}차원)로 색인했습니다."
    )
    print(f"Chroma 저장 건수: {store.count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
