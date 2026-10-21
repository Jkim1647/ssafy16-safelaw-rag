"""로컬 Chroma 컬렉션의 문서와 메타데이터를 읽기 좋게 조회한다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


COLLECTIONS = {
    "statutes": (ROOT / "data" / "indexes" / "statutes", "safelaw_statutes"),
    "cases": (ROOT / "data" / "indexes" / "cases", "safelaw_cases"),
}


def _preview(value: str, max_length: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= max_length else f"{compact[:max_length - 1]}…"


def inspect_collection(
    kind: str,
    *,
    limit: int,
    offset: int,
    category: str | None,
    max_length: int,
) -> dict[str, Any]:
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("Chroma를 사용하려면 'python -m pip install -e .'을 실행하세요.") from exc

    persist_directory, collection_name = COLLECTIONS[kind]
    if not persist_directory.exists():
        raise FileNotFoundError(f"{kind} 색인이 없습니다: {persist_directory}")

    client = chromadb.PersistentClient(path=str(persist_directory))
    available = {getattr(item, "name", item) for item in client.list_collections()}
    if collection_name not in available:
        raise RuntimeError(f"컬렉션 '{collection_name}'이 없습니다. 현재 컬렉션: {sorted(available)}")

    collection = client.get_collection(collection_name)
    where = {"category": category} if category else None
    result = collection.get(
        limit=limit,
        offset=offset,
        where=where,
        include=["documents", "metadatas"],
    )
    rows = [
        {
            "id": item_id,
            "document_preview": _preview(document or "", max_length),
            "metadata": metadata or {},
        }
        for item_id, document, metadata in zip(
            result.get("ids", []),
            result.get("documents", []),
            result.get("metadatas", []),
            strict=True,
        )
    ]
    return {
        "kind": kind,
        "path": str(persist_directory),
        "collection": collection_name,
        "total_count": collection.count(),
        "filter": {"category": category} if category else None,
        "offset": offset,
        "returned_count": len(rows),
        "rows": rows,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="SafeLaw Chroma의 저장 문서와 메타데이터를 JSON으로 조회"
    )
    parser.add_argument(
        "--collection", choices=["statutes", "cases", "all"], default="all"
    )
    parser.add_argument("--limit", type=int, default=3, help="컬렉션별 표시 건수")
    parser.add_argument("--offset", type=int, default=0, help="건너뛸 문서 수")
    parser.add_argument(
        "--category", choices=["labor", "housing_lease", "inheritance"]
    )
    parser.add_argument("--max-length", type=int, default=500, help="본문 미리보기 최대 길이")
    args = parser.parse_args()

    if args.limit < 1 or args.offset < 0 or args.max_length < 20:
        parser.error("limit은 1 이상, offset은 0 이상, max-length는 20 이상이어야 합니다.")

    kinds = COLLECTIONS if args.collection == "all" else [args.collection]
    output = [
        inspect_collection(
            kind,
            limit=args.limit,
            offset=args.offset,
            category=args.category,
            max_length=args.max_length,
        )
        for kind in kinds
    ]
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
