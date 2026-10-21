import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legal_rag.application.services import PrepareLegalQuestion
from legal_rag.domain.models import LegalCategory


class PrepareLegalQuestionTests(unittest.TestCase):
    def test_raw_identifier_does_not_cross_application_boundary(self):
        prepared = PrepareLegalQuestion().execute(
            category=LegalCategory.LABOR,
            raw_text="이름: 홍길동, 010-1234-5678로 해고 통보를 받았습니다.",
        )

        self.assertNotIn("홍길동", prepared.question.sanitized_text)
        self.assertNotIn("010-1234-5678", prepared.question.sanitized_text)
        self.assertEqual(prepared.privacy.redaction_count, 2)


if __name__ == "__main__":
    unittest.main()

