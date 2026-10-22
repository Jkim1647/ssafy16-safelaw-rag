"""한 질문으로 판례 API 캐시와 Chroma 증분 색인을 점검한다."""
from __future__ import annotations
import argparse, json, os, sys
from dataclasses import asdict
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from legal_rag.adapters.gms_embeddings import GmsEmbeddingClient  # noqa: E402
from legal_rag.adapters.gms_llm import GmsChatClient  # noqa: E402
from legal_rag.adapters.vector_store import ChromaCaseVectorStore  # noqa: E402
from legal_rag.collectors.court_cases import CourtCaseOpenApiClient  # noqa: E402
from legal_rag.domain.models import LegalCategory  # noqa: E402
from legal_rag.rag.case_enrichment import IncrementalCaseEnricher  # noqa: E402
from legal_rag.rag.case_selection import CaseCandidateSelector  # noqa: E402
from legal_rag.rag.retrieval import LegalQueryExpander  # noqa: E402
from legal_rag.security.redaction import PrivacyGuard  # noqa: E402

def main() -> int:
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="질문 기반 판례 증분 수집·색인")
    parser.add_argument("--category", required=True, choices=[x.value for x in LegalCategory])
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    gms_key, law_oc = os.getenv("GMS_KEY", "").strip(), os.getenv("LAW_API_OC", "").strip()
    if not gms_key or not law_oc:
        print("GMS_KEY와 LAW_API_OC가 모두 필요합니다.", file=sys.stderr); return 2
    base_url = os.getenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    embedding_model = os.getenv("GMS_EMBEDDING_MODEL", "text-embedding-3-small")
    query_model = os.getenv("GMS_QUERY_MODEL") or os.getenv("GMS_CHAT_MODEL", "gpt-5-nano")
    answer_model = os.getenv("GMS_ANSWER_MODEL") or "gpt-5.4-mini"
    category = LegalCategory(args.category)
    sanitized = PrivacyGuard().redact(args.query).sanitized_text
    plan = LegalQueryExpander(GmsChatClient(gms_key, model_name=query_model, base_url=base_url)).expand(sanitized, category)
    result = IncrementalCaseEnricher(
        CourtCaseOpenApiClient(law_oc),
        GmsEmbeddingClient(gms_key, model_name=embedding_model, base_url=base_url),
        ChromaCaseVectorStore(ROOT / "data/indexes/cases"),
        static_dataset=ROOT / "data/processed/cases.json",
        dynamic_dataset=ROOT / "data/cache/dynamic_cases.json",
        history_path=ROOT / "data/cache/case_collection_history.json",
        selector=CaseCandidateSelector(GmsChatClient(gms_key, model_name=answer_model, base_url=base_url)),
    ).enrich(plan, category=category)
    print(json.dumps({"cache_hit": result.cache_hit, "candidate_count": result.candidate_count,
        "new_case_count": result.new_case_count, "new_chunk_count": result.new_chunk_count,
        "case_numbers": result.case_numbers, "selection_mode": result.selection_mode,
        "candidates": [asdict(item) for item in result.decisions]}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
