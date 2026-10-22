"""LangGraph RAG 파이프라인의 노드 구조를 Mermaid로 출력한다.

그래프 구조만 보므로 GMS 키나 Chroma 색인 없이 실행할 수 있다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.rag.pipeline import StatuteRagPipeline  # noqa: E402


class _UnusedRetriever:
    def retrieve(self, sanitized_query, *, category, top_k=5):
        raise RuntimeError("구조 출력 중에는 검색을 실행하지 않습니다.")


class _UnusedLlm:
    def invoke(self, messages):
        raise RuntimeError("구조 출력 중에는 LLM을 호출하지 않습니다.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="SafeLaw LangGraph 노드 구조를 Mermaid로 출력")
    parser.add_argument("--output", type=Path, help="Mermaid 텍스트를 저장할 파일 경로")
    args = parser.parse_args()

    graph = StatuteRagPipeline(_UnusedRetriever(), _UnusedLlm()).graph.get_graph()
    mermaid = graph.draw_mermaid()
    nodes = [node for node in graph.nodes if node not in {"__start__", "__end__"}]
    edges = [f"{edge.source} -> {edge.target}" for edge in graph.edges]

    print("nodes:", ", ".join(nodes))
    print("edges:", ", ".join(edges))
    print()
    print(mermaid)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(mermaid, encoding="utf-8")


if __name__ == "__main__":
    main()
