"""체크리스트 용어 풀이가 긴 용어를 우선해 문장에 나온 순서대로 찾는지 확인한다."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.domain.glossary import ALIASES, GLOSSARY, find_terms


class GlossaryTests(unittest.TestCase):
    def test_terms_are_returned_in_order_of_appearance(self):
        terms = [term for term, _ in find_terms("확정일자를 받았고 전입신고도 했는데 대항력이 있나요?")]

        self.assertEqual(terms, ["확정일자", "전입신고", "대항력"])

    def test_longer_term_wins_over_the_term_inside_it(self):
        self.assertEqual([term for term, _ in find_terms("최우선변제 대상인가요?")], ["최우선변제"])
        self.assertEqual([term for term, _ in find_terms("해고예고수당을 못 받았어요")], ["해고예고수당"])
        self.assertEqual([term for term, _ in find_terms("유류분반환청구를 하려면")], ["유류분반환청구"])

    def test_inner_term_is_still_found_where_it_stands_alone(self):
        terms = [term for term, _ in find_terms("최우선변제와 별개로 우선변제권도 확인하세요")]

        self.assertEqual(terms, ["최우선변제", "우선변제권"])

    def test_statute_wording_maps_to_the_same_term(self):
        terms = find_terms("해고사유와 해고시기를 서면으로 통지하여야 하고, 노동위원회에 구제를 신청할 수 있다")

        self.assertEqual([term for term, _ in terms], ["서면통지", "노동위원회", "구제신청"])
        self.assertEqual([term for term, _ in find_terms("우선변제를 받을 권리")], ["우선변제권"])

    def test_every_alias_points_to_a_glossary_term(self):
        for alias, term in ALIASES.items():
            with self.subTest(alias=alias):
                self.assertIn(term, GLOSSARY)

    def test_each_term_appears_once_and_plain_text_has_none(self):
        self.assertEqual(len(find_terms("구제신청 기간과 구제신청 방법")), 1)
        self.assertEqual(find_terms("회사에서 갑자기 나오지 말라고 했어요"), [])

    def test_every_explanation_is_a_short_plain_sentence(self):
        for term, meaning in GLOSSARY.items():
            with self.subTest(term=term):
                self.assertTrue(meaning.strip())
                self.assertLessEqual(len(meaning), 120)


if __name__ == "__main__":
    unittest.main()
