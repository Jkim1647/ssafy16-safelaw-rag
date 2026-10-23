"""manifest와 수집 설정으로 제출용 데이터·API 현황 문서를 생성한다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "data-source-inventory.md"

STATUTE_LIST_GUIDE = "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide"
STATUTE_BODY_GUIDE = "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide"
CASE_LIST_GUIDE = "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precListGuide"
CASE_BODY_GUIDE = "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precInfoGuide"
USAGE_POLICY = "https://www.law.go.kr/lawPetitionForm.do?menuId=13&subMenuId=79"


def _json(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _example_env() -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _range_text(ranges: list[list[int]]) -> str:
    if not ranges:
        return "전체 조문"
    return ", ".join(f"제{start}조~제{end}조" for start, end in ranges)


def _table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    width = len(rows[0])
    return [
        "| " + " | ".join(rows[0]) + " |",
        "|" + "|".join("---" for _ in range(width)) + "|",
        *("| " + " | ".join(row) + " |" for row in rows[1:]),
    ]


def render_inventory() -> str:
    statutes = _json("data/processed/statutes_manifest.json")
    cases = _json("data/processed/cases_manifest.json")
    statute_chunks = _json("data/processed/statute_chunks_manifest.json")
    case_chunks = _json("data/processed/case_chunks_manifest.json")
    statute_sources = _json("data/statute_sources.json")
    case_sources = _json("data/case_sources.json")
    evaluation = _json("data/evaluation/statute_retrieval_results.json")
    env = _example_env()
    metrics = evaluation["metrics"]["overall"]

    law_rows = [["도메인", "법령", "수집 조문 범위", "쟁점 태그"]]
    for item in statute_sources:
        law_rows.append([
            item["category"],
            item["law_name"],
            _range_text(item.get("article_ranges", [])),
            ", ".join(item.get("issue_tags", [])),
        ])

    case_rows = [["도메인", "API 본문 검색어", "검색어별 상한"]]
    for item in case_sources:
        case_rows.append([
            item["category"],
            ", ".join(item["queries"]),
            str(item["limit_per_query"]),
        ])

    artifact_rows = [
        ["산출물", "건수", "생성 기준", "무결성"],
        ["`data/processed/statutes.json`", f"{statutes['document_count']}개 조문", statutes["collection_date"], f"SHA-256 `{statutes['dataset_sha256']}`"],
        ["`data/processed/statute_chunks.json`", f"{statute_chunks['chunk_count']}개 청크", f"최대 {statute_chunks['max_chars']}자 / 중첩 {statute_chunks['overlap_chars']}자", f"SHA-256 `{statute_chunks['dataset_sha256']}`"],
        ["`data/processed/cases.json`", f"{cases['document_count']}건", f"{cases['decision_date_range']['oldest']}~{cases['decision_date_range']['latest']} 선고", f"SHA-256 `{cases['dataset_sha256']}`"],
        ["`data/processed/case_chunks.json`", f"{case_chunks['chunk_count']}개 청크", f"최대 {case_chunks['max_chars']}자 / 중첩 {case_chunks['overlap_chars']}자", f"SHA-256 `{case_chunks['dataset_sha256']}`"],
        ["법령 Chroma", f"{statute_chunks['chunk_count']}개 벡터", "`data/indexes/statutes/`", "재생성 가능·Git 포함(바로 검증용)"],
        ["판례 Chroma", f"{case_chunks['chunk_count']}개 벡터", "`data/indexes/cases/`", "재생성 가능·Git 포함(질문 보강 증분 포함)"],
    ]

    lines = [
        "# 데이터·외부 API 현황",
        "",
        f"> 문서 기준일: {max(statutes['collection_date'], cases['collection_date'])}. 이 문서는 `python scripts/generate_data_source_inventory.py`로 manifest와 수집 설정에서 다시 생성한다.",
        "",
        "## 한눈에 보는 외부 연동",
        "",
        "| 구분 | 제공자·용도 | 요청 주소 | 인증값 | 저장 여부 |",
        "|---|---|---|---|---|",
        "| 현행법령 목록 | 법제처 국가법령정보 공동활용 | `GET https://www.law.go.kr/DRF/lawSearch.do` | `LAW_API_OC` | 응답을 조문 단위로 정규화 |",
        "| 현행법령 본문 | 법제처 국가법령정보 공동활용 | `GET https://www.law.go.kr/DRF/lawService.do` | `LAW_API_OC` | 필요한 조문과 메타데이터 저장 |",
        "| 판례 목록 | 법제처 국가법령정보 공동활용, 데이터출처 대법원 | `GET https://www.law.go.kr/DRF/lawSearch.do` | `LAW_API_OC` | 필터 통과 사건 식별자만 사용 |",
        "| 판례 본문 | 법제처 국가법령정보 공동활용, 데이터출처 대법원 | `GET https://www.law.go.kr/DRF/lawService.do` | `LAW_API_OC` | 공개·비실명 판례를 정규화 |",
        f"| 임베딩 | SSAFY GMS OpenAI 호환 API | `POST {env['GMS_BASE_URL']}/embeddings` | `GMS_KEY` | 응답 벡터를 로컬 Chroma에 저장 |",
        f"| 검색어 변환 | SSAFY GMS OpenAI 호환 API | `POST {env['GMS_BASE_URL']}/chat/completions` | `GMS_KEY` | 응답 원문 미저장, 검색계획만 사용 |",
        f"| 근거 답변 생성 | SSAFY GMS OpenAI 호환 API | `POST {env['GMS_BASE_URL']}/chat/completions` | `GMS_KEY` | 검증을 통과한 답변만 화면 표시 |",
        "| Vector DB | Chroma 로컬 저장소 | 네트워크 API 없음 | 없음 | 법령·판례 컬렉션 분리 |",
        "",
        "실제 키 값은 `.env`에만 두며 이 문서, 로그, 데이터셋, Git에는 기록하지 않는다.",
        "",
        "## 국가법령정보 API 요청 규격",
        "",
        "### 현행법령(시행일)",
        "",
        f"- 목록 공식 가이드: [{STATUTE_LIST_GUIDE}]({STATUTE_LIST_GUIDE})",
        f"- 본문 공식 가이드: [{STATUTE_BODY_GUIDE}]({STATUTE_BODY_GUIDE})",
        "- 목록 요청: `target=eflaw`, `type=JSON`, `search=1`, `query=<법령명>`, `nw=3`, `display=100`, `page=1`",
        "- 본문 요청: `target=eflaw`, `type=JSON`, `ID=<법령ID>`",
        "- 수집 필드: 법령 ID·일련번호·법령키, 조문키, 법령명, 조문번호·제목·본문, 시행일·공포일, 소관부처, 법종구분",
        "",
        "### 판례",
        "",
        f"- 목록 공식 가이드: [{CASE_LIST_GUIDE}]({CASE_LIST_GUIDE})",
        f"- 본문 공식 가이드: [{CASE_BODY_GUIDE}]({CASE_BODY_GUIDE})",
        "- 목록 요청: `target=prec`, `type=JSON`, `search=2`, `query=<쟁점 검색어>`, `display=<설정 상한>`, `page=1`",
        "- 본문 요청: `target=prec`, `type=JSON`, `ID=<판례일련번호>`",
        "- 데이터출처명이 `대법원`인 결과만 허용하고 동일 카테고리·사건번호 중복을 제거한다.",
        "- 수집 필드: 사건번호·사건명·사건종류, 법원·선고일·판결유형, 판시사항·판결요지·주문·원문, 참조조문·참조판례, 공식 URL",
        "",
        "## 실제 수집 범위",
        "",
        *_table(law_rows),
        "",
        *_table(case_rows),
        "",
        "판례 검색 결과를 그대로 저장하지 않는다. 검색어의 핵심 단어가 판시사항·판결요지·참조조문에 나타나는지 검사한 뒤 저장한다. 현재 판례 데이터는 자동 수집본이며 법률 전문가 미검수 상태다.",
        "",
        "## 현재 산출물 현황",
        "",
        *_table(artifact_rows),
        "",
        f"- 법령 카테고리: 노동 {statutes['category_counts']['labor']}개, 임대차 {statutes['category_counts']['housing_lease']}개, 상속 {statutes['category_counts']['inheritance']}개",
        f"- 판례 카테고리: 노동 {cases['category_counts']['labor']}건, 임대차 {cases['category_counts']['housing_lease']}건, 상속 {cases['category_counts']['inheritance']}건",
        f"- 판례 권위 등급: {', '.join(f'{key} {value}건' for key, value in cases['precedent_level_counts'].items())}",
        f"- 법령 검색 평가: {metrics['case_count']}문항, Recall@5 `{metrics['recall_at_5']:.3f}`, MRR `{metrics['mrr']:.3f}`, Hit@5 `{metrics['hit_at_5']:.3f}`",
        "",
        "## 모델과 호출 단계",
        "",
        "| 단계 | 기본 모델 | 외부로 전달되는 데이터 |",
        "|---|---|---|",
        f"| 문서·질문 임베딩 | `{env['GMS_EMBEDDING_MODEL']}` | 공개 법령·판례 청크 또는 마스킹된 검색문 |",
        f"| 검색어 변환 | `{env.get('GMS_QUERY_MODEL') or 'gpt-5.4-mini'}` | 마스킹된 질문과 선택 도메인 |",
        f"| 근거 답변 생성 | `{env.get('GMS_ANSWER_MODEL') or 'gpt-5.4-mini'}` | 마스킹된 질문과 검색된 공식 근거 |",
        "",
        "동일 Chroma 컬렉션을 만들 때 사용한 임베딩 모델과 검색할 때 사용하는 모델은 같아야 한다. 모델을 바꾸면 전체 색인을 다시 생성한다.",
        "",
        "## 이용 조건과 법적 효력",
        "",
        f"- 공식 안내: [국가법령정보센터 법적효력·저작권]({USAGE_POLICY})",
        "- 국가법령정보센터 제공 정보는 편의를 위한 참고자료이며, 법적 효력은 관보 등 공식 공포 자료에 있다.",
        "- 공개 법령정보는 관련 법령과 이용조건, 제3자 권리를 준수하는 범위에서 활용한다.",
        "- 출처를 국가법령정보센터·법제처로 표시하고 각 답변에 공식 원문 링크를 제공한다.",
        "- 데이터를 위조·변조하거나 법적 효력이 있는 원문인 것처럼 표시하지 않는다.",
        "- 배포·서비스 공개 전 최신 공동활용 이용조건과 신청 범위를 다시 확인한다.",
        "",
        "## 비밀값·개인정보·Git 정책",
        "",
        "| 항목 | 처리 |",
        "|---|---|",
        "| `LAW_API_OC` | `.env`에서만 읽고 URL 로그·manifest·Git에 저장하지 않음 |",
        "| `GMS_KEY` | `.env`에서만 읽고 예외·객체 표현·Git에 저장하지 않음 |",
        "| 사용자 원문 | 로컬 마스킹 후 폐기, 데이터셋·Chroma에 저장하지 않음 |",
        "| `.env` | `.gitignore` 적용(비밀값이라 데이터 중 유일하게 Git 제외) |",
        "| `data/raw/` | API 원시 응답을 저장하지 않아 비어 있음(`.gitkeep`만 Git 포함) |",
        "| `data/indexes/` | 다른 사람이 색인 없이 바로 검증하도록 Chroma 벡터 DB를 Git 포함. 키·사용자 원문은 들어 있지 않음 |",
        "| `data/cache/` | 판례 증분 보강 결과(공개 판례)와 수집 이력(마스킹 질문의 SHA-256·검색어만)을 Git 포함 |",
        "| `data/processed/` | 공개 법률 문서 정규화본과 manifest만 Git 제출 |",
        "",
        "## 재현 명령",
        "",
        "```powershell",
        "python scripts/build_statute_dataset.py",
        "python scripts/build_statute_chunks.py",
        "python scripts/build_statute_index.py",
        "python scripts/build_case_dataset.py",
        "python scripts/build_case_chunks.py",
        "python scripts/build_case_index.py",
        "python scripts/evaluate_statute_retrieval.py --no-resume",
        "python scripts/generate_data_source_inventory.py",
        "python -m unittest discover -s tests -v",
        "```",
        "",
        "## 제출 전 갱신 체크",
        "",
        "- [ ] 법령·판례를 최신 API 응답으로 다시 수집했는가?",
        "- [ ] manifest의 수집일, 건수, SHA-256이 실제 파일과 일치하는가?",
        "- [ ] 모델명이 `.env.example`, 실행 설정, 현황 문서에서 일치하는가?",
        "- [ ] 검색 평가를 캐시 없이 다시 실행했는가?",
        "- [ ] `.env`, Chroma, 원시 사용자 질문이 Git에 포함되지 않았는가?",
        "- [ ] 공식 출처와 이용 조건 링크가 README와 화면에 표시되는가?",
        "- [ ] 판례가 자동 수집본·전문가 미검수임을 명시했는가?",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUTPUT.write_text(render_inventory(), encoding="utf-8")
    print(f"데이터·API 현황 문서를 생성했습니다: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
