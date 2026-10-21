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
    STATUS_PRESENTATIONS,
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


if __name__ == "__main__":
    unittest.main()
