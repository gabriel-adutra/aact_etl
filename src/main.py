import logging
import sys
import os

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.db.aact_client import AACTClient
from src.db.neo4j_client import Neo4jClient
from src.processing.data_cleaner import DataCleaner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_pipeline(limit=1000, batch_size=500):

    logger.info("Starting ETL Pipeline (AACT -> Neo4j)...")
    
    aact_client = AACTClient()
    data_cleaner = DataCleaner()
    neo4j_client = Neo4jClient()

    neo4j_client.ensure_schema()

    try:
        trials_stream = aact_client.fetch_trials() # Generator of raw trials

        batch = []
        processed = 0

        for raw_trial in trials_stream:
            processed += 1
            if processed > limit:
                break

            clean_trial = data_cleaner.clean_study(raw_trial)
            batch.append(clean_trial)

            if processed % 100 == 0:
                logger.info(f"Processed {processed} records...")

            if len(batch) >= batch_size:
                neo4j_client.load_trials_batch(batch)
                batch = []

        # Load remaining
        if batch:
            neo4j_client.load_trials_batch(batch)

        logger.info(f"Pipeline completed successfully. Total processed: {processed}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)
    finally:
        neo4j_client.close_connection()

if __name__ == "__main__":
    # Optional: suppress overly verbose logs from submodules if needed
    logging.getLogger('src.db.aact_client').setLevel(logging.WARNING)
    run_pipeline()
