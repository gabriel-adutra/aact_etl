import os
import sys
import unittest
import logging
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.transform.data_cleaner import DataCleaner


class TestDataCleaner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger("tests.test_data_cleaner")
        cls.cleaner = DataCleaner()


    def _log_transformation(self, raw, cleaned, test_name):
        raw_json = json.dumps(raw, ensure_ascii=False, indent=2)
        cleaned_json = json.dumps(cleaned, ensure_ascii=False, indent=2)
        self.logger.info(
            f"[{test_name}]\n  Raw input:\n{raw_json}\n  Cleaned output:\n{cleaned_json}"
        )


    def _find_drug_by_name(self, drugs, name):
        return next((d for d in drugs if d["name"] == name), None)


    def _assert_drug_attributes(self, drug, expected_route, expected_dosage_form):
        self.assertEqual(drug["route"], expected_route)
        self.assertEqual(drug["dosage_form"], expected_dosage_form)
        

    def test_clean_study_with_drug_and_conditions(self):
        raw = {
            "nct_id": "NCT_UNIT_001",
            "brief_title": "  lung cancer study  ",
            "phase": "PHASE2",
            "overall_status": "RECRUITING",
            "drugs": [
                {"name": "aspirin", "description": "take one tablet orally"},
                {"name": "placebo", "description": None},
            ],
            "conditions": ["lung cancer", "Lung Cancer"],
            "sponsors": [{"name": "Pfizer Inc", "class": "INDUSTRY"}],
        }

        cleaned = self.cleaner.clean_study(raw)
        self._log_transformation(raw, cleaned, "Clean study with drug and conditions")

        self.assertEqual(cleaned["title"], "lung cancer study")
        
        self.assertEqual(len(cleaned["conditions"]), 1)
        self.assertEqual(cleaned["conditions"][0]["name"], "Lung Cancer")
        
        self.assertEqual(len(cleaned["drugs"]), 2)
        drug_names = {d["name"] for d in cleaned["drugs"]}
        self.assertIn("Aspirin", drug_names)
        
        aspirin = self._find_drug_by_name(cleaned["drugs"], "Aspirin")
        self.assertIsNotNone(aspirin)
        self._assert_drug_attributes(aspirin, "Oral", "Tablet")
        
        placebo = self._find_drug_by_name(cleaned["drugs"], "Placebo")
        self.assertIsNotNone(placebo)
        self._assert_drug_attributes(placebo, "Unknown", "Unknown")


if __name__ == "__main__":
    unittest.main()

