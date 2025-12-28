import unittest
import logging
import json

from src.transform.data_cleaner import DataCleaner


class ReadmeExampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger("tests.test_readme_example")
        cls.cleaner = DataCleaner()

    def _project_to_tabular_view(self, cleaned_trial):
        return {
            "trial": cleaned_trial["nct_id"],
            "drug": cleaned_trial["drugs"][0]["name"],
            "route": cleaned_trial["drugs"][0]["route"],
            "dosage_form": cleaned_trial["drugs"][0]["dosage_form"],
            "condition": cleaned_trial["conditions"][0]["name"],
            "sponsor": cleaned_trial["sponsors"][0]["name"],
            "sponsor_class": cleaned_trial["sponsors"][0]["class"],
        }

    def test_readme_example_transformation(self):
        raw = {
            "nct_id": "NCT00000102",
            "brief_title": "Study of Drug X in Condition Y",
            "phase": "PHASE3",
            "overall_status": "COMPLETED",
            "drugs": [
                {"name": "Drug X", "description": "Oral tablet administered daily"}
            ],
            "conditions": ["Condition Y"],
            "sponsors": [
                {"name": "Example Pharma Inc", "class": "INDUSTRY"}
            ],
        }

        expected_clean = {
            "nct_id": "NCT00000102",
            "title": "Study of Drug X in Condition Y",
            "phase": "PHASE3",
            "status": "COMPLETED",
            "drugs": [
                {"name": "Drug X", "route": "Oral", "dosage_form": "Tablet"}
            ],
            "conditions": [{"name": "Condition Y"}],
            "sponsors": [{"name": "Example Pharma Inc", "class": "INDUSTRY"}],
        }

        cleaned = self.cleaner.clean_study(raw)
        self.assertEqual(cleaned, expected_clean)

        table_row = self._project_to_tabular_view(cleaned)
        expected_table_row = {
            "trial": "NCT00000102",
            "drug": "Drug X",
            "route": "Oral",
            "dosage_form": "Tablet",
            "condition": "Condition Y",
            "sponsor": "Example Pharma Inc",
            "sponsor_class": "INDUSTRY",
        }

        self.assertEqual(table_row, expected_table_row)
        
        raw_json = json.dumps(raw, ensure_ascii=False, indent=2)
        cleaned_json = json.dumps(cleaned, ensure_ascii=False, indent=2)
        table_json = json.dumps([table_row], ensure_ascii=False, indent=2)
        self.logger.info(
            f"[README example transformation]\n  RAW input:\n{raw_json}\n  TRANSFORMED output:\n{cleaned_json}\n  Projected tabular view (Neo4j-style):\n{table_json}"
        )


if __name__ == "__main__":
    unittest.main()

