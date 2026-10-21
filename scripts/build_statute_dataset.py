"""공식 현행법령 API에서 SafeLaw 법령 조문 데이터셋을 생성한다."""

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

from legal_rag.collectors.law_api import (  # noqa: E402
    LawOpenApiClient,
    StatuteSourceConfig,
    collect_statutes,
)


def load_configs(path: Path) -> list[StatuteSourceConfig]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("법령 소스 설정은 비어 있지 않은 JSON 배열이어야 합니다.")
    return [StatuteSourceConfig.from_dict(item) for item in payload]


def serialize_document(document) -> dict:
    value = asdict(document)
    value["category"] = document.category.value
    value["effective_date"] = document.effective_date.isoformat()
    value["promulgation_date"] = (
        document.promulgation_date.isoformat() if document.promulgation_date else None
    )
    value["issue_tags"] = list(document.issue_tags)
    return value


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="SafeLaw 법령 조문 데이터셋 생성")
    parser.add_argument("--sources", type=Path, default=ROOT / "data" / "statute_sources.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "statutes.json")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "data" / "processed" / "statutes_manifest.json",
    )
    parser.add_argument("--delay", type=float, default=0.2, help="법령 본문 요청 간 대기 초")
    args = parser.parse_args()

    oc = os.getenv("LAW_API_OC", "").strip()
    if not oc:
        print("LAW_API_OC 환경변수가 필요합니다. .env 또는 현재 쉘에서 설정하세요.", file=sys.stderr)
        return 2

    configs = load_configs(args.sources)
    documents = collect_statutes(LawOpenApiClient(oc), configs, request_delay=args.delay)
    serialized = [serialize_document(item) for item in documents]
    write_json(args.output, serialized)

    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    category_counts = Counter(item.category.value for item in documents)
    law_counts = Counter(item.law_name for item in documents)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "국가법령정보센터 현행법령(시행일) Open API",
        "source_url": "https://open.law.go.kr/LSO/openApi/openApiManual.do",
        "document_count": len(documents),
        "category_counts": dict(sorted(category_counts.items())),
        "law_counts": dict(sorted(law_counts.items())),
        "dataset_sha256": digest,
        "collection_date": date.today().isoformat(),
        "source_config": args.sources.relative_to(ROOT).as_posix(),
    }
    write_json(args.manifest, manifest)

    print(f"법령 조문 {len(documents)}건을 {args.output}에 저장했습니다.")
    print(f"카테고리별: {dict(sorted(category_counts.items()))}")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
