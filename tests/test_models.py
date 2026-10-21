import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legal_rag.domain.models import LegalCategory, StatuteDocument


class StatuteDocumentTests(unittest.TestCase):
    def test_accepts_official_law_source(self):
        document = StatuteDocument(
            law_id="근로기준법-제27조",
            category=LegalCategory.LABOR,
            law_name="근로기준법",
            article_no="제27조",
            article_title="해고사유 등의 서면통지",
            text="사용자는 근로자를 해고하려면 해고사유와 해고시기를 서면으로 통지하여야 한다.",
            effective_date=date(2025, 1, 1),
            source_url="https://www.law.go.kr/정보/근로기준법/제27조",
        )
        self.assertEqual(document.category, LegalCategory.LABOR)

    def test_rejects_untrusted_source(self):
        with self.assertRaises(ValueError):
            StatuteDocument(
                law_id="x",
                category=LegalCategory.LABOR,
                law_name="근로기준법",
                article_no="제27조",
                article_title="제목",
                text="본문",
                effective_date=date(2025, 1, 1),
                source_url="http://example.com/case",
            )


if __name__ == "__main__":
    unittest.main()

