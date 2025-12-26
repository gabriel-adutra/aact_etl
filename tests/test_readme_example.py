import unittest
import logging
import json

from src.transform.data_cleaner import DataCleaner


class ReadmeExampleTest(unittest.TestCase):
    def test_readme_example_transformation(self):
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("tests.test_readme_example")

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

        cleaner = DataCleaner()
        logger.info("RAW input (README example):\n%s", json.dumps(raw, ensure_ascii=False, indent=2))
        cleaned = cleaner.clean_study(raw)
        logger.info("TRANSFORMED output:\n%s", json.dumps(cleaned, ensure_ascii=False, indent=2))

        self.assertEqual(cleaned, expected_clean)

        # Projeção tabular equivalente à consulta no Neo4j
        table_rows = [
            {
                "trial": cleaned["nct_id"],
                "drug": cleaned["drugs"][0]["name"],
                "route": cleaned["drugs"][0]["route"],
                "dosage_form": cleaned["drugs"][0]["dosage_form"],
                "condition": cleaned["conditions"][0]["name"],
                "sponsor": cleaned["sponsors"][0]["name"],
                "sponsor_class": cleaned["sponsors"][0]["class"],
            }
        ]

        expected_table = [
            {
                "trial": "NCT00000102",
                "drug": "Drug X",
                "route": "Oral",
                "dosage_form": "Tablet",
                "condition": "Condition Y",
                "sponsor": "Example Pharma Inc",
                "sponsor_class": "INDUSTRY",
            }
        ]

        self.assertEqual(table_rows, expected_table)
        logger.info("Projected tabular view (Neo4j-style):\n%s", json.dumps(table_rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    unittest.main()

