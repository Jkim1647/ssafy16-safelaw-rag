import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.config import Settings
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.pipeline import AnswerStatus
from legal_rag.ui.streamlit_app import (
    CATEGORY_LABELS,
    CHECKLIST_BLOCKED_MESSAGES,
    EXAMPLE_QUESTIONS,
    STATUS_PRESENTATIONS,
    article_question,
    case_index_status,
    chat_history,
    load_library_facts,
    parse_sensitive_terms,
    runtime_readiness,
)


def settings(*, key=None):
    return Settings(
        app_env="test",
        gms_key=key,
        gms_base_url="https://example.test/v1",
        gms_embedding_model="embedding-test",
        gms_chat_model="chat-test",
        law_api_oc=None,
    )


class StreamlitUiTests(unittest.TestCase):
    def test_every_domain_and_answer_status_has_ui_text(self):
        self.assertEqual(set(CATEGORY_LABELS), set(LegalCategory))
        self.assertEqual(set(STATUS_PRESENTATIONS), set(AnswerStatus))
        self.assertTrue(all(len(EXAMPLE_QUESTIONS[item]) >= 3 for item in LegalCategory))

    def test_sensitive_terms_are_trimmed_and_deduplicated(self):
        terms = parse_sensitive_terms("홍길동, 세이프로; 홍길동\n임대인A")

        self.assertEqual(terms, ("홍길동", "세이프로", "임대인A"))

    def test_runtime_requires_key_and_existing_index_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            index_path = Path(directory) / "statutes"
            ready_without_key, _ = runtime_readiness(settings(), index_path)
            index_path.mkdir()
            ready_with_key, _ = runtime_readiness(settings(key="test-key"), index_path)

        self.assertFalse(ready_without_key)
        self.assertTrue(ready_with_key)

    def test_chat_history_is_kept_separately_per_article(self):
        state = {}

        chat_history(state, "labor:A").append({"role": "user", "content": "A 질문"})
        chat_history(state, "labor:B").append({"role": "user", "content": "B 질문"})
        chat_history(state, "labor:A").append({"role": "assistant", "content": "A 답변"})

        self.assertEqual([m["content"] for m in chat_history(state, "labor:A")], ["A 질문", "A 답변"])
        self.assertEqual([m["content"] for m in chat_history(state, "labor:B")], ["B 질문"])

    def test_every_blocked_checklist_status_has_a_message(self):
        blocked = set(AnswerStatus) - {AnswerStatus.ANSWERED}

        self.assertEqual(set(CHECKLIST_BLOCKED_MESSAGES), blocked)

    def test_article_question_names_the_selected_article(self):
        question = article_question("근로기준법 제27조 (해고사유 등의 서면통지)", "[PERSON_1]이 카톡으로 해고했어요")

        self.assertTrue(question.startswith("[선택 조문: 근로기준법 제27조 (해고사유 등의 서면통지)]"))
        self.assertIn("[PERSON_1]이 카톡으로 해고했어요", question)



class CaseIndexStatusTests(unittest.TestCase):
    def test_missing_or_empty_case_index_means_statute_only_search(self):
        # Windows에서는 Chroma가 SQLite 파일을 잡고 있어 임시 폴더 정리 오류를 무시한다.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            missing_ready, missing_message = case_index_status(Path(folder) / "none")
            empty_ready, empty_message = case_index_status(Path(folder))

        self.assertFalse(missing_ready)
        self.assertIn("법령만 검색", missing_message)
        self.assertFalse(empty_ready)
        self.assertIn("비어", empty_message)
        self.assertFalse((Path(folder) / "none").exists())


class LibraryFactsTests(unittest.TestCase):
    def test_reads_counts_and_dates_from_the_dataset_manifests(self):
        facts = load_library_facts()

        self.assertEqual(facts.statute_articles, 381)
        self.assertEqual(facts.law_count, 4)
        self.assertEqual(facts.case_count, 50)
        self.assertEqual(facts.collected, "2026-10-21")
        self.assertEqual((facts.oldest_decision, facts.latest_decision), ("2023-08-17", "2026-06-24"))

    def test_missing_manifest_gives_no_numbers(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(load_library_facts(Path(folder) / "none.json", Path(folder) / "none.json"))


if __name__ == "__main__":
    unittest.main()
