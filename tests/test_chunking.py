import sys
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.domain.models import LegalCategory, StatuteDocument
from legal_rag.rag.chunking import chunk_statute, chunk_statutes, is_deleted_article


def make_document(text: str) -> StatuteDocument:
    return StatuteDocument(
        law_id="001872:0027001",
        category=LegalCategory.LABOR,
        law_name="근로기준법",
        article_no="제27조",
        article_title="해고사유 등의 서면통지",
        text=text,
        effective_date=date(2021, 11, 19),
        source_url="https://www.law.go.kr/법령/근로기준법/제27조",
        issue_tags=("해고", "서면통지"),
    )


class StatuteChunkingTests(unittest.TestCase):
    def test_keeps_short_article_as_one_chunk_with_search_context(self):
        chunks = chunk_statute(make_document("제27조(해고사유 등의 서면통지)\n① 사용자는 서면으로 통지하여야 한다."))

        self.assertEqual(len(chunks), 1)
        self.assertIn("법령: 근로기준법", chunks[0].embedding_text)
        self.assertIn("관련 쟁점: 해고, 서면통지", chunks[0].embedding_text)
        self.assertEqual(chunks[0].content.count("서면"), 2)

    def test_deleted_articles_are_not_chunked(self):
        deleted = replace(make_document("제35조 삭제 <2019.1.15>"), law_id="001872:0035001", article_no="제35조")
        kept = make_document("제27조(해고사유 등의 서면통지)\n① 사용자는 서면으로 통지하여야 한다.")

        chunks = chunk_statutes([deleted, kept])

        self.assertTrue(is_deleted_article(deleted))
        self.assertFalse(is_deleted_article(kept))
        self.assertEqual([chunk.article_no for chunk in chunks], ["제27조"])

    def test_article_mentioning_deletion_inside_text_is_kept(self):
        document = make_document("제27조(해고사유 등의 서면통지)\n① 사용자는 통지하여야 한다.\n② 삭제 <2014.3.24>")

        self.assertFalse(is_deleted_article(document))

    def test_splits_at_paragraph_boundaries_and_has_unique_ids(self):
        text = "\n".join(f"{number}항 " + ("법률 문장 " * 18) for number in range(1, 8))
        chunks = chunk_statute(make_document(text), max_chars=220, overlap_chars=40)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(item.content) <= 220 for item in chunks))
        self.assertEqual(len({item.chunk_id for item in chunks}), len(chunks))
        self.assertTrue(all(item.chunk_count == len(chunks) for item in chunks))

    def test_rejects_invalid_chunk_configuration(self):
        with self.assertRaises(ValueError):
            chunk_statute(make_document("본문"), max_chars=199)
        with self.assertRaises(ValueError):
            chunk_statute(make_document("본문"), overlap_chars=1200)


if __name__ == "__main__":
    unittest.main()
