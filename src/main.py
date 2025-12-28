import logging
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.extract.aact_client import AACTClient
from src.load.neo4j_client import Neo4jClient
from src.transform.data_cleaner import DataCleaner, batch_cleaned_trials


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_etl_pipeline(limit=1000, batch_size=500):

    logger.info("Starting ETL Pipeline (AACT -> Neo4j)...")
    
    aact_client = AACTClient()
    data_cleaner = DataCleaner()
    neo4j_client = Neo4jClient()

    neo4j_client.ensure_graph_schema()

    try:
        trials_stream = aact_client.fetch_trials(postgres_fetch_size=100) #just creates a generator of dictionaries. lazy function.
        for clean_batch in batch_cleaned_trials(trials_stream, data_cleaner, batch_size, limit):
            if clean_batch:
                neo4j_client.load_trials_batch(clean_batch)

        logger.info(f"Pipeline completed successfully. Next step: open http://localhost:7474, authenticate, and run the queries in queries.cypher to validate the graph.")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)
    finally:
        neo4j_client.close_connection()


if __name__ == "__main__":
    run_etl_pipeline()
