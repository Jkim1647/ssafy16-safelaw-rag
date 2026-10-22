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
