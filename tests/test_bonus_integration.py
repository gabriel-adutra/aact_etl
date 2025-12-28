import os
import unittest
import logging
import json

from src.extract.aact_client import AACTClient
from src.transform.data_cleaner import DataCleaner
from src.load.neo4j_client import Neo4jClient


class BonusIntegrationTest(unittest.TestCase):
    MAX_RECORDS = 3

    QUERY_PERSISTED_TRIALS = """
        MATCH (t:Trial)-[r:STUDIED_IN]->(d:Drug)
        WHERE t.nct_id IN $ids
        OPTIONAL MATCH (t)-[:STUDIES_CONDITION]->(c:Condition)
        OPTIONAL MATCH (t)-[s:SPONSORED_BY]->(o:Organization)
        RETURN t.nct_id AS trial,
               t.title AS title,
               d.name AS drug,
               r.route AS route,
               r.dosage_form AS dosage_form,
               collect(DISTINCT c.name) AS conditions,
               collect(DISTINCT o.name) AS sponsors
        """

    @classmethod
    def setUpClass(cls):
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger("tests.test_bonus_integration")

        missing = [env for env in ("AACT_HOST", "AACT_DB", "AACT_USER", "AACT_PASSWORD") if not os.getenv(env)]
        if missing:
            raise unittest.SkipTest(f"Skipping E2E test: missing environment variables {missing}")

        try:
            cls.aact_client = AACTClient()
            cls.data_cleaner = DataCleaner()
            cls.neo4j_client = Neo4jClient()
            cls.neo4j_client.ensure_graph_schema()
        except Exception as exc:
            raise unittest.SkipTest(f"Skipping E2E test: failed to connect ({exc})")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.neo4j_client.close_connection()
        except Exception:
            pass

    def _extract_trials(self, limit):
        stream = self.aact_client.fetch_trials()
        raw_batch = []
        for idx, row in enumerate(stream):
            if idx >= limit:
                break
            raw_batch.append(row)
        return raw_batch

    def _transform_trials(self, raw_batch):
        return [self.data_cleaner.clean_study(r) for r in raw_batch]

    def _load_trials(self, cleaned_batch):
        self.neo4j_client.load_trials_batch(cleaned_batch)

    def _query_persisted_trials(self, nct_ids):
        with self.neo4j_client.driver.session() as session:
            rows = list(session.run(self.QUERY_PERSISTED_TRIALS, ids=nct_ids))
        return [rec.data() for rec in rows]

    def _log_section(self, title, data):
        self.logger.info("-" * 80)
        self.logger.info(f"{title}:\n{json.dumps(data, ensure_ascii=False, indent=2)}")

    def _log_e2e_summary(self, raw_batch, cleaned_batch, persisted):
        raw_json = json.dumps(raw_batch, ensure_ascii=False, indent=2)
        cleaned_json = json.dumps(cleaned_batch, ensure_ascii=False, indent=2)
        persisted_json = json.dumps(persisted, ensure_ascii=False, indent=2)
        
        self.logger.info("-" * 80)
        self.logger.info(
            f"[E2E Real Small Batch]\n"
            f"  Extracted {len(raw_batch)} records from stream (of many available from AACT)\n{raw_json}\n"
            f"  Transformed: {len(cleaned_batch)} records\n{cleaned_json}\n"
            f"  Persisted in Neo4j: {len(cleaned_batch)} trials\n"
            f"  Query result: {len(persisted)} trial-drug relationship{'s' if len(persisted) != 1 else ''}\n{persisted_json}"
        )

    def test_e2e_real_small_batch(self):
        raw_batch = self._extract_trials(self.MAX_RECORDS)
        self.assertGreater(len(raw_batch), 0, "No records extracted; check AACT credentials.")

        cleaned_batch = self._transform_trials(raw_batch)
        self.assertEqual(len(cleaned_batch), len(raw_batch))

        self._load_trials(cleaned_batch)

        nct_ids = [c["nct_id"] for c in cleaned_batch if c.get("nct_id")]
        persisted = self._query_persisted_trials(nct_ids)
        self.assertGreater(len(persisted), 0, "No data found in Neo4j for extracted NCT IDs.")
        
        self._log_e2e_summary(raw_batch, cleaned_batch, persisted)


if __name__ == "__main__":
    unittest.main()

