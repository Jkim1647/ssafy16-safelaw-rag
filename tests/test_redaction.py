import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legal_rag.security.redaction import PrivacyGuard


class PrivacyGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = PrivacyGuard()

    def test_redacts_common_identifiers_before_external_processing(self):
        original = (
            "이름: 홍길동, 주민번호 900101-1234567, "
            "전화 010-1234-5678, 메일 gildong@example.com"
        )

        result = self.guard.redact(original)

        self.assertNotIn("홍길동", result.sanitized_text)
        self.assertNotIn("900101-1234567", result.sanitized_text)
        self.assertNotIn("010-1234-5678", result.sanitized_text)
        self.assertNotIn("gildong@example.com", result.sanitized_text)
        self.assertEqual(result.redaction_count, 4)

    def test_reuses_placeholder_for_repeated_custom_term(self):
        result = self.guard.redact(
            "ABC전자에서 해고됐고 ABC전자에 서면을 요청했다.",
            extra_terms=["ABC전자"],
        )

        self.assertEqual(result.sanitized_text.count("[CUSTOM_1]"), 2)
        self.assertEqual(result.redaction_count, 1)

    def test_redacts_road_address(self):
        result = self.guard.redact("임차 주택은 서울특별시 강남구 테헤란로 123에 있습니다.")
        self.assertNotIn("테헤란로 123", result.sanitized_text)
        self.assertIn("[ADDRESS_1]", result.sanitized_text)

    def test_submission_example_has_stable_masking_preview(self):
        original = (
            "이름: 홍길동, 주민번호 991332-1234567, 전화 010-0000-0000, "
            "메일 gildong@example.com, 주소 서울특별시 강남구 테헤란로 000입니다."
        )

        result = self.guard.redact(original)

        self.assertEqual(
            result.sanitized_text,
            "이름: [PERSON_1], 주민번호 [RRN_1], 전화 [PHONE_1], "
            "메일 [EMAIL_1], 주소 [ADDRESS_1]입니다.",
        )
        self.assertEqual(result.redaction_count, 5)

    def test_repr_does_not_include_original_secret(self):
        result = self.guard.redact("전화번호는 010-9999-8888입니다.")
        self.assertNotIn("010-9999-8888", repr(result))
        self.assertNotIn("010-9999-8888", repr(result.entities[0]))

    def test_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            self.guard.redact("   ")


class CustomTermAmplificationTests(unittest.TestCase):
    def test_custom_terms_do_not_rewrite_existing_placeholders(self):
        terms = ["C", "U", "S", "T", "O", "M", "_", "1", "2", "[", "]", "PHONE"]

        result = PrivacyGuard().redact("C 010-1234-5678", terms)

        self.assertLess(len(result.sanitized_text), 40)
        self.assertIn("[PHONE_1]", result.sanitized_text)
        self.assertTrue(result.sanitized_text.startswith("[CUSTOM_1]"))

    def test_longer_custom_term_wins_over_its_substring(self):
        result = PrivacyGuard().redact("세이프로 주식회사와 세이프로", ["세이프로", "세이프로 주식회사"])

        self.assertEqual(result.sanitized_text, "[CUSTOM_1]와 [CUSTOM_2]")


if __name__ == "__main__":
    unittest.main()

