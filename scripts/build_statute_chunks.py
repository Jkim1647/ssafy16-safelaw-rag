"""정규화 법령 데이터셋을 조문 구조 기반 청크로 변환한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.domain.models import LegalCategory, StatuteDocument  # noqa: E402
from legal_rag.rag.chunking import chunk_statutes  # noqa: E402


def load_documents(path: Path) -> list[StatuteDocument]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        StatuteDocument(
            **{
                **item,
                "category": LegalCategory(item["category"]),
                "effective_date": date.fromisoformat(item["effective_date"]),
                "promulgation_date": (
                    date.fromisoformat(item["promulgation_date"])
                    if item.get("promulgation_date")
                    else None
                ),
                "issue_tags": tuple(item.get("issue_tags", [])),
            }
        )
        for item in payload
    ]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="SafeLaw 법령 청크 생성")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "processed" / "statutes.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "statute_chunks.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "processed" / "statute_chunks_manifest.json")
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--overlap-chars", type=int, default=150)
    args = parser.parse_args()

    documents = load_documents(args.input)
    chunks = chunk_statutes(
        documents,
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
    )
    serialized = []
    for chunk in chunks:
        item = asdict(chunk)
        item["category"] = chunk.category.value
        item["issue_tags"] = list(chunk.issue_tags)
        serialized.append(item)
    write_json(args.output, serialized)

    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "source_dataset": args.input.relative_to(ROOT).as_posix(),
        "source_dataset_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "category_counts": dict(sorted(Counter(item.category.value for item in chunks).items())),
        "max_chars": args.max_chars,
        "overlap_chars": args.overlap_chars,
        "dataset_sha256": digest,
    }
    write_json(args.manifest, manifest)
    print(f"법령 {len(documents)}건을 {len(chunks)}개 청크로 변환했습니다.")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
