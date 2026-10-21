"""정규화 판례를 섹션 기반 청크로 변환한다."""

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

from legal_rag.domain.models import CaseDocument, LegalCategory, PrecedentLevel  # noqa: E402
from legal_rag.rag.case_chunking import chunk_cases  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="SafeLaw 판례 청크 생성")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "processed" / "cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "case_chunks.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "processed" / "case_chunks_manifest.json")
    parser.add_argument("--max-chars", type=int, default=1400)
    parser.add_argument("--overlap-chars", type=int, default=180)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    documents = [CaseDocument(**{**item, "category": LegalCategory(item["category"]),
        "decision_date": date.fromisoformat(item["decision_date"]),
        "precedent_level": PrecedentLevel(item.get("precedent_level", "other")),
        "issues": tuple(item.get("issues", [])),
        "related_articles": tuple(item.get("related_articles", []))}) for item in payload]
    chunks = chunk_cases(documents, max_chars=args.max_chars, overlap_chars=args.overlap_chars)
    serialized = []
    for chunk in chunks:
        item = asdict(chunk)
        item["category"] = chunk.category.value
        item["precedent_level"] = chunk.precedent_level.value
        item["related_articles"] = list(chunk.related_articles)
        serialized.append(item)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(serialized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema_version": 2, "source_dataset": args.input.relative_to(ROOT).as_posix(),
        "source_dataset_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "document_count": len(documents), "chunk_count": len(chunks),
        "category_counts": dict(sorted(Counter(item.category.value for item in chunks).items())),
        "section_counts": dict(sorted(Counter(item.section for item in chunks).items())),
        "max_chars": args.max_chars, "overlap_chars": args.overlap_chars,
        "dataset_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"판례 {len(documents)}건을 {len(chunks)}개 섹션 청크로 변환했습니다.")
    print(f"섹션별: {manifest['section_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
