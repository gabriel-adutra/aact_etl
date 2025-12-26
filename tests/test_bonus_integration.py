import os
import unittest
import logging
import json

from src.extract.aact_client import AACTClient
from src.transform.data_cleaner import DataCleaner
from src.load.neo4j_client import Neo4jClient


class BonusIntegrationTest(unittest.TestCase):
    """
    Bônus (E2E real pequeno): extrai poucos registros reais do AACT, transforma e carrega no Neo4j.
    Mostra o que foi extraído, transformado e persistido.
    """

    MAX_RECORDS = 3

    @classmethod
    def setUpClass(cls):
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger("tests.test_bonus_integration")

        missing = [env for env in ("AACT_HOST", "AACT_DB", "AACT_USER", "AACT_PASSWORD") if not os.getenv(env)]
        if missing:
            raise unittest.SkipTest(f"Pulando teste E2E real: faltam variáveis {missing}")

        try:
            cls.aact = AACTClient()
            cls.cleaner = DataCleaner()
            cls.neo = Neo4jClient()
            cls.neo.ensure_graph_schema()
        except Exception as exc:
            raise unittest.SkipTest(f"Pulando teste E2E real: não foi possível conectar ({exc})")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.neo.close_connection()
        except Exception:
            pass

    def test_e2e_real_small_batch(self):
        # 1) Extrair até MAX_RECORDS
        stream = self.aact.fetch_trials()
        raw_batch = []
        for idx, row in enumerate(stream):
            if idx >= self.MAX_RECORDS:
                break
            raw_batch.append(row)

        self.logger.info("-" * 80)
        self.logger.info("Abaixo estão %s registros extraídos da AACT):\n%s", self.MAX_RECORDS, json.dumps(raw_batch, ensure_ascii=False, indent=2))
        self.assertGreater(len(raw_batch), 0, "Nenhum registro extraído; verifique credenciais/AACT.")

        # 2) Transformar
        cleaned_batch = [self.cleaner.clean_study(r) for r in raw_batch]
        self.logger.info("-" * 80)
        self.logger.info("Abaixo estão os %s registros transformados após limpeza e inferência:\n%s", self.MAX_RECORDS, json.dumps(cleaned_batch, ensure_ascii=False, indent=2))
        self.assertEqual(len(cleaned_batch), len(raw_batch))

        # 3) Carregar no Neo4j
        self.neo.load_trials_batch(cleaned_batch)

        # 4) Consultar no Neo4j para confirmar persistência
        nct_ids = [c["nct_id"] for c in cleaned_batch if c.get("nct_id")]
        cypher = """
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
        with self.neo.driver.session() as session:
            rows = list(session.run(cypher, ids=nct_ids))

        persisted = [rec.data() for rec in rows]
        self.logger.info("-" * 80)
        self.logger.info("Abaixo estão as entidades e relações persistidas no Neo4j:\n%s", json.dumps(persisted, ensure_ascii=False, indent=2))
        self.assertGreater(len(rows), 0, "Nenhum dado encontrado no Neo4j para os NCT extraídos.")


if __name__ == "__main__":
    unittest.main()

