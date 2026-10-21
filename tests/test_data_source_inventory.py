import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_data_source_inventory import OUTPUT, render_inventory


class DataSourceInventoryTests(unittest.TestCase):
    def test_generated_inventory_is_up_to_date(self):
        self.assertEqual(OUTPUT.read_text(encoding="utf-8"), render_inventory())

    def test_inventory_covers_sources_credentials_and_usage_policy(self):
        content = render_inventory()
        for expected in (
            "target=eflaw",
            "target=prec",
            "LAW_API_OC",
            "GMS_KEY",
            "Chroma",
            "법적효력·저작권",
            "SHA-256",
        ):
            self.assertIn(expected, content)


if __name__ == "__main__":
    unittest.main()
