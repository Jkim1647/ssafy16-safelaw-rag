"""판례 검색 평가셋 라벨의 기계적 일관성을 검사하고 검수 보고서를 생성한다."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALUATION = ROOT / "data" / "evaluation" / "case_retrieval_cases.json"
DEFAULT_CASES = ROOT / "data" / "processed" / "cases.json"
DEFAULT_JSON_REPORT = ROOT / "data" / "evaluation" / "case_label_audit.json"
DEFAULT_MARKDOWN_REPORT = ROOT / "docs" / "case-evaluation-label-audit.md"
VALID_CATEGORIES = {"labor", "housing_lease", "inheritance"}
VALID_REVIEW_STATUSES = {"developer_labeled", "approved", "needs_change", "out_of_scope"}
OFFICIAL_HOSTS = {"law.go.kr", "www.law.go.kr"}


def load_json(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"JSON 배열이 필요합니다: {path}")
    return payload


def audit_labels(
    evaluation_rows: list[dict[str, object]],
    case_rows: list[dict[str, object]],
) -> dict[str, object]:
    cases_by_number = {str(item.get("case_number", "")): item for item in case_rows}
    ids = [str(item.get("id", "")) for item in evaluation_rows]
    categories = Counter(str(item.get("category", "")) for item in evaluation_rows)
    review_statuses = Counter(str(item.get("review_status", "")) for item in evaluation_rows)
    errors: list[str] = []
    warnings: list[str] = []
    details: list[dict[str, object]] = []

    if len(ids) != len(set(ids)):
        errors.append("평가 문항 ID가 중복되었습니다.")
    if len(evaluation_rows) != 30:
        errors.append(f"평가 문항은 30개여야 하지만 {len(evaluation_rows)}개입니다.")
    for category in sorted(VALID_CATEGORIES):
        if categories[category] != 10:
            errors.append(f"{category} 문항은 10개여야 하지만 {categories[category]}개입니다.")
    unknown_categories = set(categories) - VALID_CATEGORIES
    if unknown_categories:
        errors.append("지원하지 않는 카테고리: " + ", ".join(sorted(unknown_categories)))

    for row in evaluation_rows:
        row_id = str(row.get("id", ""))
        category = str(row.get("category", ""))
        query = str(row.get("query", "")).strip()
        expected = [str(value) for value in row.get("expected_case_numbers", [])]
        acceptable = [str(value) for value in row.get("acceptable_case_numbers", [])]
        review_status = str(row.get("review_status", ""))
        row_errors: list[str] = []
        row_warnings: list[str] = []
        linked_cases: list[dict[str, object]] = []

        if not row_id or not query:
            row_errors.append("ID 또는 질문이 비어 있습니다.")
        if not expected:
            row_errors.append("기대 사건번호가 없습니다.")
        if set(expected) & set(acceptable):
            row_errors.append("기대 사건번호와 허용 사건번호가 중복됩니다.")
        if review_status not in VALID_REVIEW_STATUSES:
            row_errors.append(f"허용하지 않는 검수 상태: {review_status}")

        for role, numbers in (("expected", expected), ("acceptable", acceptable)):
            for number in numbers:
                case = cases_by_number.get(number)
                if case is None:
                    row_errors.append(f"원본 판례 데이터에 없는 {role} 사건번호: {number}")
                    continue
                case_category = str(case.get("category", ""))
                source_url = str(case.get("source_url", ""))
                host = urlparse(source_url).hostname or ""
                if case_category != category:
                    row_warnings.append(
                        f"{number} 카테고리 불일치: 평가={category}, 판례={case_category}"
                    )
                if host not in OFFICIAL_HOSTS:
                    row_errors.append(f"{number} 공식 국가법령정보 URL 확인 실패: {source_url}")
                linked_cases.append(
                    {
                        "role": role,
                        "case_number": number,
                        "case_name": str(case.get("case_name", "")),
                        "court": str(case.get("court", "")),
                        "decision_date": str(case.get("decision_date", "")),
                        "source_url": source_url,
                    }
                )

        errors.extend(f"{row_id}: {message}" for message in row_errors)
        warnings.extend(f"{row_id}: {message}" for message in row_warnings)
        details.append(
            {
                "id": row_id,
                "category": category,
                "query": query,
                "review_status": review_status,
                "mechanical_status": "pass" if not row_errors else "fail",
                "cases": linked_cases,
                "errors": row_errors,
                "warnings": row_warnings,
            }
        )

    if review_statuses.get("developer_labeled", 0):
        warnings.append(
            f"법률 전문가 미검수 문항 {review_statuses['developer_labeled']}개가 남아 있습니다."
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "evaluation_count": len(evaluation_rows),
            "source_case_count": len(case_rows),
            "unique_id_count": len(set(ids)),
            "category_counts": dict(sorted(categories.items())),
            "review_status_counts": dict(sorted(review_statuses.items())),
            "mechanical_check": "pass" if not errors else "fail",
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
        "items": details,
    }


def markdown_report(report: dict[str, object]) -> str:
    summary = report["summary"]
    assert isinstance(summary, dict)
    items = report["items"]
    assert isinstance(items, list)
    lines = [
        "# 판례 평가셋 라벨 사전 감사",
        "",
        "> 이 문서는 평가셋의 파일·사건번호·카테고리·공식 URL 일관성을 자동 검사한 결과다. "
        "법률적 관련성, 판례의 변경·폐기 여부, 최신·상급심 판례 누락 여부에 대한 전문가 승인을 대체하지 않는다.",
        "",
        "## 검사 결과",
        "",
        f"- 기계적 검사: **{summary['mechanical_check']}**",
        f"- 평가 문항: **{summary['evaluation_count']}개**",
        f"- 원본 판례: **{summary['source_case_count']}개**",
        f"- 고유 ID: **{summary['unique_id_count']}개**",
        f"- 도메인별 문항: `{summary['category_counts']}`",
        f"- 검수 상태: `{summary['review_status_counts']}`",
        f"- 오류: **{summary['error_count']}개** · 경고: **{summary['warning_count']}개**",
        "",
        "자동 검사 범위는 다음과 같다.",
        "",
        "- 30문항 및 도메인별 10문항 구성",
        "- 문항 ID 중복 여부",
        "- 기대·허용 사건번호의 원본 데이터 존재 여부",
        "- 평가 문항과 판례의 카테고리 일치 여부",
        "- 국가법령정보 공식 원문 URL 여부",
        "- 검수 상태 값과 기대·허용 사건번호 중복 여부",
        "",
        "## 문항별 원문 연결",
        "",
        "| ID | 질문 | 기대 판례 | 허용 판례 | 기계 검사 | 전문가 상태 |",
        "|---|---|---|---|---|---|",
    ]
    for item in items:
        assert isinstance(item, dict)
        expected_links: list[str] = []
        acceptable_links: list[str] = []
        for case in item["cases"]:
            assert isinstance(case, dict)
            label = (
                f"{case['case_number']} · {case['court']} · {case['decision_date']}"
            )
            link = f"[{label}]({case['source_url']})"
            if case["role"] == "expected":
                expected_links.append(link)
            else:
                acceptable_links.append(link)
        query = str(item["query"]).replace("|", "\\|")
        lines.append(
            "| {id} | {query} | {expected} | {acceptable} | {mechanical} | {review} |".format(
                id=item["id"],
                query=query,
                expected="<br>".join(expected_links) or "-",
                acceptable="<br>".join(acceptable_links) or "-",
                mechanical=item["mechanical_status"],
                review=item["review_status"],
            )
        )
    lines.extend(
        [
            "",
            "## 외부 검수자가 확인할 항목",
            "",
            "- 질문의 사실관계와 기대 판례의 핵심 쟁점이 직접 연결되는가",
            "- 허용 판례가 Top-5 정답으로 인정될 만큼 관련성이 있는가",
            "- 더 최신이거나 권위 있는 대법원·전원합의체 판례가 누락되지 않았는가",
            "- 후속 판례로 변경·제한·폐기된 법리가 없는가",
            "- 검수 결과와 수정 사유를 `case-evaluation-review-sheet.md`에 기록했는가",
            "",
            "외부 검수와 서명이 끝날 때까지 JSON의 `review_status`는 "
            "`developer_labeled`로 유지한다.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="판례 평가셋 라벨 사전 감사")
    parser.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-report", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    args = parser.parse_args()

    report = audit_labels(load_json(args.evaluation), load_json(args.cases))
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_report.write_text(markdown_report(report), encoding="utf-8")
    summary = report["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["mechanical_check"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
