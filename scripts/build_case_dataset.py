"""공식 판례 API에서 SafeLaw 판례 데이터셋을 생성한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.collectors.court_cases import (  # noqa: E402
    CaseSourceConfig, CourtCaseOpenApiClient, collect_cases,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SafeLaw 대법원 공개 판례 데이터셋 생성")
    parser.add_argument("--sources", type=Path, default=ROOT / "data" / "case_sources.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "cases.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "processed" / "cases_manifest.json")
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    oc = os.getenv("LAW_API_OC", "").strip()
    if not oc:
        print("LAW_API_OC 환경변수가 필요합니다.", file=sys.stderr)
        return 2
    payload = json.loads(args.sources.read_text(encoding="utf-8"))
    configs = [CaseSourceConfig.from_dict(item) for item in payload]
    documents = collect_cases(CourtCaseOpenApiClient(oc), configs, request_delay=args.delay)
    serialized = []
    for document in documents:
        item = asdict(document)
        item["category"] = document.category.value
        item["decision_date"] = document.decision_date.isoformat()
        item["precedent_level"] = document.precedent_level.value
        item["issues"] = list(document.issues)
        item["related_articles"] = list(document.related_articles)
        serialized.append(item)
    write_json(args.output, serialized)
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection_date": date.today().isoformat(),
        "source": "국가법령정보센터 판례 Open API(데이터출처: 대법원)",
        "source_url": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precListGuide",
        "document_count": len(documents),
        "category_counts": dict(sorted(Counter(item.category.value for item in documents).items())),
        "precedent_level_counts": dict(sorted(Counter(item.precedent_level.value for item in documents).items())),
        "dataset_sha256": digest,
        "source_config": args.sources.relative_to(ROOT).as_posix(),
    }
    write_json(args.manifest, manifest)
    print(f"대법원 공개 판례 {len(documents)}건을 저장했습니다.")
    print(f"카테고리별: {manifest['category_counts']}")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
