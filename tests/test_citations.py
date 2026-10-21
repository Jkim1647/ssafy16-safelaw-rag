import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.rag.citations import (
    CitationValidationError,
    build_statute_evidence,
    parse_and_validate_draft,
    render_grounded_answer,
)
from legal_rag.rag.retrieval import RetrievedChunk


def hit(
    *,
    chunk_id="labor-27",
    article_no="제27조",
    source_url="https://www.law.go.kr/법령/근로기준법/제27조",
):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document="사용자는 근로자를 해고하려면 해고사유와 해고시기를 서면으로 통지하여야 한다.",
        metadata={
            "law_name": "근로기준법",
            "article_no": article_no,
            "article_title": "해고사유 등의 서면통지",
            "source_url": source_url,
        },
        distance=0.1,
    )


class CitationValidationTests(unittest.TestCase):
    def test_build_evidence_keeps_only_official_law_sources(self):
        evidence = build_statute_evidence(
            [
                hit(),
                hit(chunk_id="untrusted", source_url="https://example.com/fake"),
            ]
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].citation_id, 1)
        self.assertIn("law.go.kr", evidence[0].source_url)

    def test_validates_and_renders_only_known_citations(self):
        evidence = build_statute_evidence([hit()])
        raw = json.dumps(
            {
                "answerable": True,
                "summary": {
                    "text": "제27조는 서면 통지를 요구합니다.",
                    "citations": [1],
                    "evidence_quotes": [
                        {"citation_id": 1, "quote": "해고사유와 해고시기를 서면으로 통지"}
                    ],
                },
                "issues": [
                    {
                        "text": "서면 통지 여부를 확인해야 합니다.",
                        "citations": [1],
                        "evidence_quotes": [
                            {"citation_id": 1, "quote": "서면으로 통지하여야 한다"}
                        ],
                    }
                ],
                "favorable_factors": [],
                "unfavorable_factors": [],
                "additional_facts": [],
                "next_steps": [],
            },
            ensure_ascii=False,
        )

        draft = parse_and_validate_draft(raw, evidence)
        rendered = render_grounded_answer(draft, evidence)

        self.assertIn("[근거 1]", rendered)
        self.assertIn(evidence[0].source_url, rendered)

    def test_rejects_claim_without_citation(self):
        evidence = build_statute_evidence([hit()])
        raw = json.dumps(
            {
                "answerable": True,
                "summary": {"text": "근거 없는 주장", "citations": [], "evidence_quotes": []},
            },
            ensure_ascii=False,
        )

        with self.assertRaises(CitationValidationError):
            parse_and_validate_draft(raw, evidence)

    def test_rejects_article_not_linked_to_cited_evidence(self):
        evidence = build_statute_evidence([hit()])
        raw = json.dumps(
            {
                "answerable": True,
                "summary": {
                    "text": "제28조에 따라 구제받습니다.",
                    "citations": [1],
                    "evidence_quotes": [
                        {"citation_id": 1, "quote": "해고사유와 해고시기를 서면으로 통지"}
                    ],
                },
            },
            ensure_ascii=False,
        )

        with self.assertRaises(CitationValidationError):
            parse_and_validate_draft(raw, evidence)

    def test_rejects_quote_not_found_in_retrieved_law(self):
        evidence = build_statute_evidence([hit()])
        raw = json.dumps(
            {
                "answerable": True,
                "summary": {
                    "text": "회사는 위자료를 지급해야 합니다.",
                    "citations": [1],
                    "evidence_quotes": [
                        {"citation_id": 1, "quote": "회사는 위자료를 지급하여야 한다"}
                    ],
                },
            },
            ensure_ascii=False,
        )

        with self.assertRaises(CitationValidationError):
            parse_and_validate_draft(raw, evidence)


if __name__ == "__main__":
    unittest.main()
