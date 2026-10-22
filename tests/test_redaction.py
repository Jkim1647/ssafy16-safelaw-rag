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

    def test_hyphenated_dates_stay_for_deadline_reasoning(self):
        text = "2026-10-01에 해고됐고 2026-1-5에 통지서를 받았어요. 26-10-01 이후 연락이 없어요."

        result = PrivacyGuard().redact(text)

        self.assertEqual(result.sanitized_text, text)
        self.assertEqual(result.redaction_count, 0)

    def test_account_numbers_are_still_redacted_next_to_dates(self):
        result = PrivacyGuard().redact("2026-10-01까지 110-123-456789 계좌와 1002-123-456789 계좌로 보증금을 받기로 했어요.")

        self.assertIn("2026-10-01", result.sanitized_text)
        self.assertNotIn("110-123-456789", result.sanitized_text)
        self.assertNotIn("1002-123-456789", result.sanitized_text)
        self.assertEqual([entity.kind for entity in result.entities], ["ACCOUNT", "ACCOUNT"])

    def test_impossible_month_or_day_is_not_treated_as_a_date(self):
        result = PrivacyGuard().redact("계좌 2026-13-40으로 보내 주세요.")

        self.assertNotIn("2026-13-40", result.sanitized_text)


if __name__ == "__main__":
    unittest.main()

