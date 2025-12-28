import os
import sys
import unittest
import logging
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.transform.text_parser import TextParser


class TestTextParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger("tests.test_text_parser")
        cls.parser = TextParser("config/text_rules.yaml")


    def _log_inference_result(self, input_text, result, test_name):
        input_display = input_text if input_text is not None else "None"
        result_json = json.dumps(result, ensure_ascii=False, indent=2)
        self.logger.info(
            f"[{test_name}]\n  Input: {input_display}\n  Result:\n{result_json}"
        )


    def _assert_route_and_form(self, result, expected_route, expected_form=None):
        self.assertEqual(result["route"], expected_route)
        if expected_form is not None:
            if isinstance(expected_form, set):
                self.assertIn(result["dosage_form"], expected_form)
            else:
                self.assertEqual(result["dosage_form"], expected_form)


    def test_infer_oral_tablet(self):
        text = "Patients will take 10mg tablet orally twice a day."
        result = self.parser.infer_route_and_form(text)
        self._log_inference_result(text, result, "Oral/Tablet")
        self._assert_route_and_form(result, "Oral", "Tablet")


    def test_infer_intravenous(self):
        text = "Drug administered via IV infusion over 30 minutes."
        result = self.parser.infer_route_and_form(text)
        self._log_inference_result(text, result, "Intravenous")
        self._assert_route_and_form(result, "Intravenous", {"Unknown", "Injection"})
        

    def test_infer_unknown_on_empty(self):
        result = self.parser.infer_route_and_form(None)
        self._log_inference_result(None, result, "Empty input")
        self._assert_route_and_form(result, "Unknown", "Unknown")


if __name__ == "__main__":
    unittest.main()

