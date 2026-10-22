import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.config import Settings


RAG_KEYS = (
    "STATUTE_CHUNK_SIZE",
    "STATUTE_CHUNK_OVERLAP",
    "CASE_CHUNK_SIZE",
    "CASE_CHUNK_OVERLAP",
    "RAG_TOP_K",
    "RAG_SEARCH_MODE",
    "RAG_MMR_FETCH_K",
    "RAG_MMR_LAMBDA",
)


def load(**values):
    environment = {key: value for key, value in os.environ.items() if key not in RAG_KEYS}
    environment.update(values)
    with mock.patch.dict(os.environ, environment, clear=True), \
            mock.patch("legal_rag.config.load_dotenv"):
        return Settings.from_environment()


class RagSettingsTests(unittest.TestCase):
    def test_defaults_match_current_index(self):
        settings = load()

        self.assertEqual((settings.statute_chunk_size, settings.statute_chunk_overlap), (1200, 150))
        self.assertEqual((settings.case_chunk_size, settings.case_chunk_overlap), (1400, 180))
        self.assertEqual(settings.rag_top_k, 5)

    def test_values_are_read_from_environment(self):
        settings = load(
            STATUTE_CHUNK_SIZE="600",
            STATUTE_CHUNK_OVERLAP="80",
            CASE_CHUNK_SIZE="900",
            CASE_CHUNK_OVERLAP="0",
            RAG_TOP_K="3",
        )

        self.assertEqual((settings.statute_chunk_size, settings.statute_chunk_overlap), (600, 80))
        self.assertEqual((settings.case_chunk_size, settings.case_chunk_overlap), (900, 0))
        self.assertEqual(settings.rag_top_k, 3)

    def test_query_model_defaults_to_fast_answer_model_and_can_be_overridden(self):
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("GMS_QUERY_MODEL", "GMS_CHAT_MODEL", "GMS_ANSWER_MODEL")}
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch("legal_rag.config.load_dotenv"):
            default = Settings.from_environment()
        with mock.patch.dict(os.environ, {**environment, "GMS_QUERY_MODEL": "gpt-5-nano"}, clear=True), \
                mock.patch("legal_rag.config.load_dotenv"):
            override = Settings.from_environment()

        self.assertEqual(default.query_model, "gpt-5.4-mini")
        self.assertEqual(override.query_model, "gpt-5-nano")

    def test_search_mode_settings(self):
        defaults = load()
        mmr = load(RAG_SEARCH_MODE="MMR", RAG_MMR_FETCH_K="20", RAG_MMR_LAMBDA="0.7")

        self.assertEqual((defaults.rag_search_mode, defaults.rag_mmr_fetch_k, defaults.rag_mmr_lambda),
                         ("similarity", 30, 0.5))
        self.assertEqual((mmr.rag_search_mode, mmr.rag_mmr_fetch_k, mmr.rag_mmr_lambda), ("mmr", 20, 0.7))
        for values in ({"RAG_SEARCH_MODE": "random"}, {"RAG_MMR_LAMBDA": "1.5"}, {"RAG_MMR_FETCH_K": "0"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                load(**values)

    def test_blank_value_uses_default(self):
        self.assertEqual(load(RAG_TOP_K="").rag_top_k, 5)

    def test_rejects_invalid_values(self):
        for values in (
            {"RAG_TOP_K": "0"},
            {"RAG_TOP_K": "five"},
            {"STATUTE_CHUNK_SIZE": "150"},
            {"STATUTE_CHUNK_SIZE": "500", "STATUTE_CHUNK_OVERLAP": "500"},
            {"CASE_CHUNK_OVERLAP": "-1"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                load(**values)


if __name__ == "__main__":
    unittest.main()
