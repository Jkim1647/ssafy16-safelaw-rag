"""셀프·상호 체크리스트의 명령 출력 증빙을 실행하고 PNG로 저장한다.

기본 실행은 GMS를 부르지 않는 항목만 다룬다. GMS가 필요한 판례 수집(3·4번)과
Top-k·MMR 비교(6·16번)는 --with-gms를 줄 때만 실행한다.

    .\\.venv\\Scripts\\python.exe scripts\\capture_checklist_evidence.py
    .\\.venv\\Scripts\\python.exe scripts\\capture_checklist_evidence.py --only c03 c06 --with-gms
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Sequence
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import dotenv_values  # noqa: E402

from legal_rag.adapters.vector_store import ChromaCaseVectorStore, ChromaStatuteVectorStore  # noqa: E402
from legal_rag.config import Settings  # noqa: E402
from legal_rag.domain.models import CaseDocument  # noqa: E402
from legal_rag.rag.case_chunking import chunk_cases  # noqa: E402
from legal_rag.rag.chunking import chunk_statutes, is_deleted_article  # noqa: E402
from legal_rag.rag.indexing import index_chunks  # noqa: E402

OUTPUT_DIR = ROOT / "docs" / "checklist"
PYTHON = sys.executable
# 판례 수집 증빙용 질문. 기존 수집 이력에 없는 새 질문이어야 첫 실행에서 수집이 일어난다.
ENRICH_QUESTION = "수습기간 3개월째인데 회사가 수습이라 정당한 이유 없이 본채용을 거절할 수 있다고 합니다."
EVIDENCE_QUESTION = "팀장이 카카오톡으로 내일부터 나오지 말라고 했고 해고 사유가 적힌 문서는 받지 못했어요."


def _run(args: Sequence[str]) -> str:
    completed = subprocess.run(
        [PYTHON, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    return (completed.stdout + completed.stderr).strip() + f"\n\n(종료 코드 {completed.returncode})"


def _load_statutes():
    from build_statute_chunks import load_documents

    return load_documents(ROOT / "data" / "processed" / "statutes.json")


def _load_cases(path: Path) -> list[CaseDocument]:
    from legal_rag.rag.case_enrichment import _document_from_dict

    if not path.exists():
        return []
    return [_document_from_dict(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def c01_counts() -> str:
    documents = _load_statutes()
    kept = [item for item in documents if not is_deleted_article(item)]
    settings = Settings.from_environment()
    chunks = json.loads((ROOT / "data/processed/statute_chunks.json").read_text(encoding="utf-8"))
    statute_store = ChromaStatuteVectorStore(ROOT / "data/indexes/statutes")
    case_chunks = json.loads((ROOT / "data/processed/case_chunks.json").read_text(encoding="utf-8"))
    dynamic = _load_cases(ROOT / "data/cache/dynamic_cases.json")
    dynamic_chunks = chunk_cases(dynamic, max_chars=settings.case_chunk_size, overlap_chars=settings.case_chunk_overlap)
    case_store = ChromaCaseVectorStore(ROOT / "data/indexes/cases")
    sample = next(item for item in chunks if item["chunk_id"] == "labor:001872:0027001:000")
    lines = [
        "[법령]",
        f"로드한 조문: {len(documents)}건 (본문이 '삭제'뿐인 조문 {len(documents) - len(kept)}건 제외 → {len(kept)}건)",
        f"청크 파일 statute_chunks.json: {len(chunks)}개  (1,200자를 넘는 조문만 2개 이상으로 나뉨)",
        f"Chroma safelaw_statutes 컬렉션: {statute_store.count}개  → 일치: {len(chunks) == statute_store.count}",
        "",
        "[판례]",
        f"정적 청크 case_chunks.json: {len(case_chunks)}개 + 질문 시 증분 보강 판례 {len(dynamic)}건의 청크 {len(dynamic_chunks)}개",
        f"Chroma safelaw_cases 컬렉션: {case_store.count}개  → 일치: {len(case_chunks) + len(dynamic_chunks) == case_store.count}",
        "",
        f"[항목 1건의 색인 텍스트] chunk_id = {sample['chunk_id']}",
        sample["embedding_text"][:420] + " …",
    ]
    return "\n".join(lines)


class _FixedEmbedder:
    """GMS를 부르지 않고 색인 경로만 실행하기 위한 고정 벡터."""

    model_name = "fixed-test-vector"

    def embed(self, texts):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def c02_reindex() -> str:
    from legal_rag.domain.models import LegalCategory
    from legal_rag.rag.chunking import StatuteChunk

    raw = json.loads((ROOT / "data/processed/statute_chunks.json").read_text(encoding="utf-8"))
    chunks = [StatuteChunk(**{**item, "category": LegalCategory(item["category"]),
                              "issue_tags": tuple(item.get("issue_tags", []))}) for item in raw]
    lines = ["실제 index_chunks() 코드로 같은 청크 382개를 새 Chroma에 두 번 색인 (임베딩은 GMS 대신 고정 벡터)"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        store = ChromaStatuteVectorStore(Path(folder))
        for run in (1, 2):
            index_chunks(chunks, _FixedEmbedder(), store)
            lines.append(f"{run}회 색인 후 컬렉션 청크 수: {store.count}")
    lines.append("청크 ID가 분야·법령/조문 ID·청크 순번으로 고정되어 upsert가 덮어쓰므로 두 번 실행해도 늘지 않음")
    return "\n".join(lines)


def c05_chunk_sizes() -> str:
    statutes = [item for item in _load_statutes() if not is_deleted_article(item)]
    cases = _load_cases(ROOT / "data/processed/cases.json")
    lines = ["설정(STATUTE_CHUNK_SIZE/STATUTE_CHUNK_OVERLAP, CASE_CHUNK_SIZE/CASE_CHUNK_OVERLAP) 값별 청크 수"]
    for size, overlap in ((1200, 150), (800, 150), (500, 100)):
        lines.append(f"법령 {size}자 / 중복 {overlap}자 → {len(chunk_statutes(statutes, max_chars=size, overlap_chars=overlap))}개")
    for size, overlap in ((1400, 180), (1000, 200), (700, 100)):
        lines.append(f"판례 {size}자 / 중복 {overlap}자 → {len(chunk_cases(cases, max_chars=size, overlap_chars=overlap))}개")
    lines.append("(청크 수는 임베딩 전에 정해지므로 GMS 호출 없이 청킹 단계까지 실행)")
    return "\n".join(lines)


def _unittest(names: Sequence[str]) -> str:
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromNames(list(names))
    with contextlib.redirect_stderr(io.StringIO()):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return stream.getvalue().strip() + f"\n\n성공 {result.testsRun - len(result.failures) - len(result.errors)} / 전체 {result.testsRun}"


def c10_conversation_isolation() -> str:
    sys.path.insert(0, str(ROOT / "tests"))
    return _unittest([
        "test_streamlit_ui.StreamlitUiTests.test_chat_history_is_kept_separately_per_article",
        "test_consultation_room.ConsultationRoomTests.test_new_consultation_starts_a_new_thread",
        "test_pipeline.StatuteRagPipelineTests.test_conversation_threads_are_isolated_and_single_answers_have_no_history",
    ])


def c13_guidance() -> str:
    sys.path.insert(0, str(ROOT / "tests"))
    return _unittest([
        "test_streamlit_ui.StreamlitUiTests.test_runtime_requires_key_and_existing_index_directory",
        "test_streamlit_ui.CaseIndexStatusTests",
        "test_consultation_room.CaseIndexNoticeTests",
        "test_web_api.WebApiTests.test_status_reports_statute_only_search_without_case_index",
    ])


def c07_graph() -> str:
    return "$ python scripts/show_rag_graph.py\n\n" + _run(["scripts/show_rag_graph.py"])


def c21_secrets() -> str:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout

    tracked = git("ls-files", ".env", "data/indexes", "data/raw", "data/cache").strip()
    values = [value for key, value in dotenv_values(ROOT / ".env").items()
              if key in {"GMS_KEY", "LAW_API_OC"} and value and len(value) > 3]
    found = sum(git("grep", "-c", "-F", value).count(":") for value in values)
    patterns = git("grep", "-n", "-E", r"sk-[A-Za-z0-9]{16,}|S[0-9]{2}P[0-9A-Z]{6,}|BEGIN (RSA|OPENSSH) PRIVATE").strip()
    config = (ROOT / ".streamlit/config.toml").read_text(encoding="utf-8")
    return "\n".join([
        "$ git ls-files .env data/indexes data/raw data/cache",
        tracked or "(추적 파일 없음)",
        "",
        f"$ .env의 GMS_KEY·LAW_API_OC 실제 값({len(values)}개)을 추적 파일 전체에서 검색 → {found}건",
        "$ 키 형태 패턴(sk-…, S..P…, 개인키) 검색 → " + (patterns or "0건"),
        "",
        "[.streamlit/config.toml] " + next(line for line in config.splitlines() if "showErrorDetails" in line),
        "[web/api.py] 처리하지 못한 오류는 고정 문구 GENERIC_ERROR만 응답하고 상세는 서버 로그에만 남김",
        "화면 확인: c21_error_screen.png (내부 예외 메시지가 화면에 나오지 않음)",
    ])


def c22_modules() -> str:
    lines = ["src/legal_rag/"]
    for folder in sorted(path for path in (ROOT / "src/legal_rag").iterdir() if path.is_dir() and path.name != "__pycache__"):
        files = sorted(item.name for item in folder.iterdir() if item.suffix in {".py", ".js", ".html", ".css"} and item.name != "__init__.py")
        lines.append(f"  {folder.name}/  " + ", ".join(files))
    return "\n".join(lines)


def c23_api_etiquette() -> str:
    lines = []
    for name in ("law_api.py", "court_cases.py"):
        source = (ROOT / "src/legal_rag/collectors" / name).read_text(encoding="utf-8").splitlines()
        lines.append(f"[collectors/{name}]")
        for number, line in enumerate(source, start=1):
            if any(word in line for word in ("User-Agent", "retry_delay", "max_retries", "time.sleep", "request_delay")):
                lines.append(f"{number:4}: {line.strip()}")
        lines.append("")
    return "\n".join(lines).strip()


def c24_sources() -> str:
    inventory = (ROOT / "docs/data-source-inventory.md").read_text(encoding="utf-8").splitlines()
    readme = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(readme) if line.startswith("## 데이터 출처와 이용 시 주의사항"))
    return "\n".join(["[README.md]", *readme[start:start + 9], "", "[docs/data-source-inventory.md]", *inventory[:16]])


def c20_response_time() -> str:
    text = (ROOT / "docs/verification-results.md").read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(text) if line.startswith("응답 시간 측정"))
    end = next(index for index in range(start + 2, len(text)) if not text[index].startswith("|"))
    return "\n".join(["[docs/verification-results.md 4.7절 · 2026-10-22 실제 서버 측정]", *text[start:end],
                      "", "실행 1 = 처음 묻는 질문, 실행 2 = 같은 질문을 다시 물은 경우",
                      "판례 수집이 새로 일어나는 질문은 c03_c04_enrichment_cache.png에서 보강 단계만 1회차 33.0초 → 2회차 11.7초"])


def c03_c04_enrichment() -> str:
    command = ["scripts/enrich_case_index.py", "--category", "labor", "--query", ENRICH_QUESTION]
    lines = [f"질문: {ENRICH_QUESTION}", ""]
    for run in (1, 2):
        output = _run(command)
        body = output[: output.rfind("(종료 코드")].strip()
        data = json.loads(body[body.index("{"):])
        lines.append(f"[{run}회차] 처리 시간 {data['elapsed_seconds']}초 · cache_hit={data['cache_hit']} · "
                     f"후보 {data['candidate_count']}건 · 새로 색인 {data['new_case_count']}건 · 선별 방식 {data['selection_mode']}")
        lines.append("  프롬프트1 검색어: " + ", ".join(data["legal_terms"]))
        for item in data["candidates"]:
            lines.append(f"  - {item['decision']:<9} {item['case_number']:<14} {item['case_name'][:34]}")
        lines.append("")
    return "\n".join(lines).strip()


def c06_c16_topk_mmr() -> str:
    command = ["scripts/show_evidence.py", EVIDENCE_QUESTION, "--category", "labor", "--compare-search", "--top-k", "3", "5"]
    return f"$ python scripts/show_evidence.py \"{EVIDENCE_QUESTION}\" --category labor --compare-search --top-k 3 5\n\n" + _run(command)


STEPS: dict[str, tuple[str, Callable[[], str], bool]] = {
    "c01": ("1 · F2001 로드 건수와 색인 청크 수, 색인 텍스트", c01_counts, False),
    "c02": ("2 · F2002 색인 두 번 실행", c02_reindex, False),
    "c03": ("3·4 · F2003·F2004·NF2002 검색어·선별 결과와 재질문 시 수집 생략", c03_c04_enrichment, True),
    "c05": ("5 · F2005 청크 크기·중복 길이별 청크 수", c05_chunk_sizes, False),
    "c06": ("6·16 · F2006·F2014 Top-k 변경과 유사도/MMR 근거 비교", c06_c16_topk_mmr, True),
    "c07": ("7 · F2007 LangGraph 노드 구성", c07_graph, False),
    "c10": ("10 · F2009 항목·상담별 대화 분리 테스트", c10_conversation_isolation, False),
    "c13": ("13 · F2012 키 없음·색인 없음 안내 테스트", c13_guidance, False),
    "c20": ("20 · NF2001 첫 질문·두 번째 질문 처리 시간", c20_response_time, False),
    "c21": ("21 · NF2003·NF2004 키 미포함·오류 비노출", c21_secrets, False),
    "c22": ("22 · NF2005 모듈 분리", c22_modules, False),
    "c23": ("23 · NF2006 재시도·호출 간격·User-Agent", c23_api_etiquette, False),
    "c24": ("24 · NF2007 출처·이용 조건 기록", c24_sources, False),
}
FILE_NAMES = {
    "c01": "c01_f2001_counts.png", "c02": "c02_f2002_reindex.png", "c03": "c03_c04_enrichment_cache.png",
    "c05": "c05_f2005_chunk_sizes.png", "c06": "c06_c16_topk_mmr.png", "c07": "c07_f2007_langgraph.png",
    "c10": "c10_f2009_isolation_tests.png", "c13": "c13_f2012_guidance_tests.png", "c20": "c20_nf2001_response_time.png",
    "c21": "c21_nf2003_secrets.png",
    "c22": "c22_nf2005_modules.png", "c23": "c23_nf2006_api_etiquette.png", "c24": "c24_nf2007_sources.png",
}


def _scrub(text: str) -> str:
    for key, value in dotenv_values(ROOT / ".env").items():
        if key in {"GMS_KEY", "LAW_API_OC"} and value and len(value) > 3:
            text = text.replace(value, "<숨김>")
    return text


def render(title: str, body: str, output: Path) -> None:
    from render_architecture import find_chrome

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = (
        "<!doctype html><meta charset='utf-8'><style>"
        "body{margin:0;background:#fff;font-family:'Malgun Gothic',sans-serif;color:#111827}"
        "header{background:#1f2c3d;color:#fff;padding:14px 22px}"
        "h1{margin:0;font-size:20px}p{margin:4px 0 0;font-size:13px;opacity:.85}"
        "pre{margin:0;padding:18px 22px;font-family:'D2Coding','Consolas','Malgun Gothic',monospace;"
        "font-size:14px;line-height:1.55;white-space:pre-wrap;word-break:break-all}</style>"
        f"<header><h1>{escape(title)}</h1><p>SafeLaw 셀프 체크리스트 증빙 · {stamp} 실행</p></header>"
        f"<pre>{escape(body)}</pre>"
    )
    lines = sum(max(1, len(line) // 120 + 1) for line in body.splitlines()) + 2
    height = 90 + lines * 22 + 40
    with tempfile.TemporaryDirectory(prefix="safelaw-evidence-") as folder:
        page = Path(folder) / "page.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [str(find_chrome()), "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--user-data-dir={Path(folder) / 'profile'}", f"--window-size=1280,{height}",
             "--force-device-scale-factor=1.5", f"--screenshot={output}", page.as_uri()],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
        )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="셀프 체크리스트 명령 출력 증빙 PNG 생성")
    parser.add_argument("--only", nargs="+", choices=sorted(STEPS), help="일부 항목만 실행")
    parser.add_argument("--with-gms", action="store_true", help="GMS가 필요한 항목(c03, c06)도 실행")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for key in args.only or sorted(STEPS):
        title, step, needs_gms = STEPS[key]
        if needs_gms and not args.with_gms:
            print(f"{key}: 건너뜀 (GMS 필요, --with-gms로 실행)")
            continue
        body = _scrub(step())
        output = OUTPUT_DIR / FILE_NAMES[key]
        render(title, body, output)
        print(f"{key}: {output.relative_to(ROOT)}")
        print(body)
        print("-" * 60)


if __name__ == "__main__":
    main()
