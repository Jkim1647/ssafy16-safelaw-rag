"""심화 F2015: 같은 질문을 RAG 없이 한 번, 근거를 붙여 한 번 답하게 해 비교한다.

RAG 없는 답변도 같은 답변 생성 모델을 쓰고 법령 조문을 함께 제시하라고 요청한다.
답변에서 언급한 조문을 수집된 법령 데이터셋과 대조해 존재 여부를 기록하고,
기대 조문을 언급·인용했는지 표시한다. 최종 판정은 문서에서 사람이 기록한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.adapters.gms_llm import GmsChatClient  # noqa: E402
from legal_rag.config import Settings  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.citations import CaseEvidence  # noqa: E402
from legal_rag.ui.streamlit_app import build_pipeline  # noqa: E402


QUESTIONS = (
    ("labor-dismissal", LegalCategory.LABOR,
     "회사에서 카카오톡으로 내일부터 나오지 말라고 했어요. 이런 해고도 효력이 있나요?",
     ("근로기준법 제27조",)),
    ("labor-final-pay", LegalCategory.LABOR,
     "퇴사했는데 마지막 월급을 회사가 다음 달에 주겠다고 해요. 언제까지 줘야 하나요?",
     ("근로기준법 제36조",)),
    ("housing-auction", LegalCategory.HOUSING_LEASE,
     "전입신고와 확정일자를 마친 세입자인데 집이 경매로 넘어갔어요. 보증금을 먼저 받을 수 있나요?",
     ("주택임대차보호법 제3조의2",)),
    ("inheritance-renounce", LegalCategory.INHERITANCE,
     "부모님 빚이 재산보다 많아요. 상속포기는 언제까지 해야 하나요?",
     ("민법 제1019조",)),
    ("inheritance-sibling-reserve", LegalCategory.INHERITANCE,
     "돌아가신 형이 전 재산을 지인에게 줬어요. 동생인 제가 유류분을 청구할 수 있나요?",
     ("민법 제1112조",)),
    ("unanswerable-article", LegalCategory.LABOR,
     "근로기준법 제200조는 무엇을 규정하고 있나요?",
     ()),
)

ARTICLE_PATTERN = re.compile(
    r"(근로기준법|주택임대차보호법|민법|기간제법|기간제 및 단시간근로자 보호 등에 관한 법률)"
    r"\s*(?:제\s*)?(\d+)\s*조(?:\s*의\s*(\d+))?"
)
BASELINE_SYSTEM = (
    "당신은 대한민국 생활법률 정보를 설명하는 도우미다. 질문에 한국어로 답하고 근거가 되는 "
    "법령 조문 번호를 함께 제시한다. 확실하지 않은 내용은 모른다고 답한다."
)


def article_mentions(text: str) -> list[str]:
    mentions: list[str] = []
    for law, number, branch in ARTICLE_PATTERN.findall(text):
        law = "기간제 및 단시간근로자 보호 등에 관한 법률" if law == "기간제법" else law
        label = f"{law} 제{number}조" + (f"의{branch}" if branch else "")
        if label not in mentions:
            mentions.append(label)
    return mentions


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="RAG 사용 전후 답변 비교")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "evaluation" / "rag_before_after.json")
    args = parser.parse_args()

    settings = Settings.from_environment()
    if not settings.gms_key:
        print("GMS_KEY가 필요합니다.", file=sys.stderr)
        return 2
    # 실시간 판례 보강을 끄고 저장소 색인만으로 비교해 재현성을 높인다.
    pipeline = build_pipeline(replace(settings, law_api_oc=None))
    baseline_llm = GmsChatClient(settings.gms_key, model_name=settings.answer_model, base_url=settings.gms_base_url)
    statutes = json.loads((ROOT / "data" / "processed" / "statutes.json").read_text(encoding="utf-8"))
    known_articles = {f"{item['law_name']} {item['article_no']}" for item in statutes}

    results = []
    for item_id, category, question, expected in QUESTIONS:
        baseline = baseline_llm.invoke([
            {"role": "system", "content": BASELINE_SYSTEM},
            {"role": "user", "content": question},
        ])
        baseline_mentions = article_mentions(baseline)
        answer = pipeline.answer(question, category=category, top_k=settings.rag_top_k)
        cited_statutes = [
            f"{source.law_name} {source.article_no}"
            for source in answer.sources if not isinstance(source, CaseEvidence)
        ]
        results.append({
            "id": item_id,
            "category": category.value,
            "question": question,
            "expected_articles": list(expected),
            "baseline": {
                "answer": baseline,
                "mentioned_articles": baseline_mentions,
                "articles_not_in_dataset": [label for label in baseline_mentions if label not in known_articles],
                "expected_mentioned": [label for label in expected if label in baseline_mentions],
                "has_source_link": bool(re.search(r"https?://", baseline)),
            },
            "rag": {
                "status": answer.status.value,
                "answer": answer.content,
                "cited_statutes": cited_statutes,
                "cited_cases": [source.label for source in answer.sources if isinstance(source, CaseEvidence)],
                "expected_cited": [label for label in expected if label in cited_statutes],
            },
        })
        print(f"{item_id}: 기준 조문 언급 {results[-1]['baseline']['expected_mentioned']} / "
              f"RAG {answer.status.value} 인용 {results[-1]['rag']['expected_cited']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "answer_model": settings.answer_model,
        "search_mode": settings.rag_search_mode,
        "top_k": settings.rag_top_k,
        "review_status": "자동 대조 후 개발자 판정 · 법률 전문가 미검수",
        "results": results,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {args.output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
