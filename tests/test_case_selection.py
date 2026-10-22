import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.collectors.court_cases import CaseSearchResult
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.case_selection import CaseCandidateSelector, CaseSelectionError
from legal_rag.rag.retrieval import SearchPlan


CANDIDATES = (
    CaseSearchResult("1", "2099다1", "임대차보증금반환", "대법원", date(2099, 1, 1), "판결", "대법원"),
    CaseSearchResult("2", "2099두2", "부당해고구제재심판정취소", "대법원", date(2099, 1, 2), "판결", "대법원"),
)
PLAN = SearchPlan("[PERSON_1]이 카톡으로 해고", "카카오톡 해고 통보와 서면통지", ("부당해고", "서면통지"), True)


class FakeLlm:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.response


class CaseCandidateSelectorTests(unittest.TestCase):
    def test_returns_selected_indexes_with_reasons(self):
        llm = FakeLlm('{"selected": [{"id": "P2", "reason": "부당해고 구제 판단"}]}')

        picks = CaseCandidateSelector(llm).select(PLAN, LegalCategory.LABOR, CANDIDATES)

        self.assertEqual(picks, [(1, "부당해고 구제 판단")])

    def test_prompt_shows_titles_and_legal_terms_but_not_masked_question(self):
        llm = FakeLlm('{"selected": []}')

        CaseCandidateSelector(llm).select(PLAN, LegalCategory.LABOR, CANDIDATES)

        prompt = "\n".join(message["content"] for message in llm.messages)
        self.assertIn("[P2] 2099두2", prompt)
        self.assertIn("부당해고구제재심판정취소", prompt)
        self.assertIn("서면통지", prompt)
        self.assertNotIn("[PERSON_1]", prompt)

    def test_ignores_unknown_and_duplicate_ids(self):
        llm = FakeLlm('{"selected": [{"id": "P7"}, {"id": "P1"}, {"id": "P1"}, {"id": "C2"}]}')

        picks = CaseCandidateSelector(llm).select(PLAN, LegalCategory.LABOR, CANDIDATES)

        self.assertEqual(picks, [(0, "")])

    def test_invalid_output_raises_selection_error(self):
        with self.assertRaises(CaseSelectionError):
            CaseCandidateSelector(FakeLlm("판단할 수 없습니다")).select(PLAN, LegalCategory.LABOR, CANDIDATES)

    def test_llm_failure_raises_selection_error(self):
        with self.assertRaises(CaseSelectionError):
            CaseCandidateSelector(FakeLlm(error=RuntimeError("down"))).select(
                PLAN, LegalCategory.LABOR, CANDIDATES
            )


if __name__ == "__main__":
    unittest.main()
