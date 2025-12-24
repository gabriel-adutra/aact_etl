import os
import logging
from typing import List, Dict, Any
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        
        self.driver = self._create_driver(uri, user, password)
        

    def _create_driver(self, uri: str, user: str, password: str):
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {uri}")
            return driver
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
        

    def close_connection(self):
        if self.driver:
            self.driver.close()


    def ensure_graph_schema(self):
        queries = [
            # Constraints (Uniqueness)
            "CREATE CONSTRAINT trial_nct_id IF NOT EXISTS FOR (t:Trial) REQUIRE t.nct_id IS UNIQUE",
            "CREATE CONSTRAINT drug_name IF NOT EXISTS FOR (d:Drug) REQUIRE d.name IS UNIQUE",
            "CREATE CONSTRAINT condition_name IF NOT EXISTS FOR (c:Condition) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT org_name IF NOT EXISTS FOR (o:Organization) REQUIRE o.name IS UNIQUE",
            
            # Indexes (Performance)
            "CREATE INDEX trial_phase IF NOT EXISTS FOR (t:Trial) ON (t.phase)",
            "CREATE INDEX trial_status IF NOT EXISTS FOR (t:Trial) ON (t.status)"
        ]
        
        with self.driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                    logger.info(f"Schema applied: {q}")
                except Exception as e:
                    logger.warning(f"Schema query failed (might already exist): {e}")
                    

    def load_trials_batch(self, batch: List[Dict[str, Any]]):
        if not batch:
            return

        cypher = """
        UNWIND $batch AS data
        
        // 1. Create Trial Node
        MERGE (t:Trial {nct_id: data.nct_id})
        SET t.title = data.title, 
            t.phase = data.phase, 
            t.status = data.status,
            t.last_updated = datetime()

        // 2. Process Drugs
        FOREACH (d IN data.drugs |
            MERGE (drug:Drug {name: d.name})
            MERGE (t)-[r:STUDIED_IN]->(drug)
            // Set properties on relationship only if known
            FOREACH (_ IN CASE WHEN d.route <> 'Unknown' THEN [1] ELSE [] END | SET r.route = d.route)
            FOREACH (_ IN CASE WHEN d.dosage_form <> 'Unknown' THEN [1] ELSE [] END | SET r.dosage_form = d.dosage_form)
        )

        // 3. Process Conditions
        FOREACH (c IN data.conditions |
            MERGE (cond:Condition {name: c.name})
            MERGE (t)-[:STUDIES_CONDITION]->(cond)
        )

        // 4. Process Sponsors
        FOREACH (s IN data.sponsors |
            MERGE (org:Organization {name: s.name})
            MERGE (t)-[:SPONSORED_BY {class: s.class}]->(org)
        )
        """
        
        with self.driver.session() as session:
            try:
                session.run(cypher, batch=batch)
                logger.info(f"Loaded batch of {len(batch)} trials to Neo4j.")
            except Exception as e:
                logger.error(f"Failed to load batch: {e}")
                raise

