"""셀프·상호 체크리스트의 명령 출력 증빙을 실행하고 PNG로 저장한다.

재색인(2·5번), 판례 수집(3·4번), Top-k·MMR 비교(6·16번)는 GMS를 실제로 호출하므로
--with-gms를 줄 때만 실행한다. 앱 화면 증빙은 실제 서버를 띄워 따로 캡처한다.

    .\\.venv\\Scripts\\python.exe scripts\\capture_checklist_evidence.py --with-gms
    .\\.venv\\Scripts\\python.exe scripts\\capture_checklist_evidence.py --only c01 c07
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
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
from legal_rag.rag.chunking import is_deleted_article  # noqa: E402

OUTPUT_DIR = ROOT / "docs" / "checklist"
PYTHON = sys.executable
# 판례 수집 증빙용 질문. 기존 수집 이력에 없는 새 질문이어야 첫 실행에서 수집이 일어난다.
ENRICH_CATEGORY = "inheritance"
ENRICH_QUESTION = "아버지가 돌아가시기 전에 형에게만 아파트를 증여했는데 저도 유류분 반환을 청구할 수 있나요?"
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


def c02_reindex() -> str:
    lines = ["실제 색인 스크립트를 같은 임시 폴더에 두 번 실행 (GMS 임베딩 사용)", ""]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        for run in (1, 2):
            output = _run(["scripts/build_statute_index.py", "--persist-dir", folder])
            lines.append(f"[{run}회차] $ python scripts/build_statute_index.py --persist-dir <임시 폴더>")
            lines.append(output)
            lines.append("")
    lines.append("색인 스크립트는 컬렉션을 새로 만들고, 청크 ID(분야·법령/조문 ID·청크 순번)로 저장해 다시 실행해도 청크 수가 늘지 않음")
    return "\n".join(lines)


def c05_chunk_sizes() -> str:
    lines = ["설정값을 바꿔 실제 청킹·색인 스크립트를 실행 (원본 데이터 파일은 바꾸지 않도록 임시 폴더에 출력)", ""]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        root = Path(folder)
        for size, overlap in ((1200, 150), (800, 150)):
            chunks = root / f"statute_{size}.json"
            lines.append(f"$ python scripts/build_statute_chunks.py --max-chars {size} --overlap-chars {overlap}")
            lines.append(_run(["scripts/build_statute_chunks.py", "--max-chars", str(size), "--overlap-chars", str(overlap),
                               "--output", str(chunks), "--manifest", str(root / f"statute_{size}_manifest.json")]))
            lines.append(f"$ python scripts/build_statute_index.py (위 청크로 재색인)")
            lines.append(_run(["scripts/build_statute_index.py", "--input", str(chunks), "--persist-dir", str(root / f"index_{size}")]))
            lines.append("")
        for size, overlap in ((1400, 180), (1000, 200)):
            lines.append(f"$ python scripts/build_case_chunks.py --max-chars {size} --overlap-chars {overlap}")
            lines.append(_run(["scripts/build_case_chunks.py", "--max-chars", str(size), "--overlap-chars", str(overlap),
                               "--output", str(root / f"case_{size}.json"), "--manifest", str(root / f"case_{size}_manifest.json")]))
            lines.append("")
    return "\n".join(lines).strip()


def c17_before_after() -> str:
    text = (ROOT / "docs/rag-before-after.md").read_text(encoding="utf-8").splitlines()
    return "\n".join(["[docs/rag-before-after.md]", *text[:40]])


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
        "화면 확인: 21_오류_화면.png (실제 서버에서 GMS 주소를 잘못 넣어 낸 오류, 내부 예외 메시지가 화면에 나오지 않음)",
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


def c03_c04_enrichment() -> str:
    command = ["scripts/enrich_case_index.py", "--category", ENRICH_CATEGORY, "--query", ENRICH_QUESTION]
    lines = [f"질문: {ENRICH_QUESTION}", ""]
    for run in (1, 2):
        output = _run(command)
        body = output[: output.rfind("(종료 코드")].strip()
        data = json.loads(body[body.index("{"):])
        lines.append(f"[{run}회차] 전체 {data['elapsed_seconds']}초 = 검색어 변환 {data['query_seconds']}초 + "
                     f"판례 수집 {data['collection_seconds']}초 · cache_hit={data['cache_hit']}")
        lines.append(f"  후보 {data['candidate_count']}건 · 새로 색인 {data['new_case_count']}건 · 선별 방식 {data['selection_mode']}")
        lines.append("  프롬프트1 검색어: " + ", ".join(data["legal_terms"]))
        for item in data["candidates"]:
            lines.append(f"  - {item['decision']:<9} {item['case_number']:<14} {item['case_name'][:34]}")
        lines.append("")
    return "\n".join(lines).strip()


def c06_c16_topk_mmr() -> str:
    command = ["scripts/show_evidence.py", EVIDENCE_QUESTION, "--category", "labor", "--compare-search", "--top-k", "3", "5"]
    return f"$ python scripts/show_evidence.py \"{EVIDENCE_QUESTION}\" --category labor --compare-search --top-k 3 5\n\n" + _run(command)


# (제목, 실행 함수, GMS 필요 여부, 저장 파일명). 파일명은 양식 예시처럼 번호를 앞에 붙인 한글 이름이다.
STEPS: dict[str, tuple[str, Callable[[], str], bool, str]] = {
    "c01": ("1 · F2001 로드 건수와 색인 청크 수, 색인 텍스트", c01_counts, False, "01_색인_건수_일치.png"),
    "c02": ("2 · F2002 색인 두 번 실행", c02_reindex, True, "02_재색인_청크수_유지.png"),
    "c03": ("3·4 · F2003·F2004·NF2002 검색어·선별 결과와 재질문 시 수집 생략", c03_c04_enrichment, True,
            "03_04_검색어_선별_재질문_캐시.png"),
    "c05": ("5 · F2005 청크 크기·중복 길이를 바꿔 재색인", c05_chunk_sizes, True, "05_청크설정별_청크수.png"),
    "c06": ("6·16 · F2006·F2014 Top-k 변경과 유사도/MMR 근거 비교", c06_c16_topk_mmr, True, "06_16_TopK_유사도_MMR_비교.png"),
    "c07": ("7 · F2007 LangGraph 노드 구성", c07_graph, False, "07_LangGraph_노드구성.png"),
    "c17": ("17·18 · F2015 RAG 사용 전후 비교 기록", c17_before_after, False, "17_18_RAG_전후비교_문서.png"),
    "c21": ("21 · NF2003·NF2004 저장소 키 검색과 오류 비노출 설정", c21_secrets, False, "21_키_검색_결과.png"),
    "c22": ("22 · NF2005 모듈 분리", c22_modules, False, "22_모듈_구성.png"),
    "c23": ("23 · NF2006 재시도·호출 간격·User-Agent", c23_api_etiquette, False, "23_외부호출_재시도_헤더.png"),
    "c24": ("24 · NF2007 출처·이용 조건 기록", c24_sources, False, "24_출처_이용조건.png"),
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
    parser.add_argument("--with-gms", action="store_true", help="GMS를 실제로 호출하는 항목(c02, c03, c05, c06)도 실행")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for key in args.only or sorted(STEPS):
        title, step, needs_gms, file_name = STEPS[key]
        if needs_gms and not args.with_gms:
            print(f"{key}: 건너뜀 (GMS 필요, --with-gms로 실행)")
            continue
        body = _scrub(step())
        output = OUTPUT_DIR / file_name
        render(title, body, output)
        print(f"{key}: {output.relative_to(ROOT)}")
        print(body)
        print("-" * 60)


if __name__ == "__main__":
    main()
