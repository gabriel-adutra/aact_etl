import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Generator, Dict, Any, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from psycopg2.extensions import connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AACTClient:
    def __init__(self) -> None:
        self.conn_params = {
            "host": os.getenv("AACT_HOST"),
            "port": os.getenv("AACT_PORT"),
            "database": os.getenv("AACT_DB"),
            "user": os.getenv("AACT_USER"),
            "password": os.getenv("AACT_PASSWORD"),
        }

        
    def _get_connection(self) -> "connection":
        try:
            return psycopg2.connect(**self.conn_params)
        except Exception as e:
            logger.error(f"Failed to connect to AACT Database: {e}")
            raise


    def fetch_trials(self, query_path: str = "config/extract_trials.sql", postgres_fetch_size: int = 100) -> Generator[Dict[str, Any], None, None]:
        if not os.path.exists(query_path):
            raise FileNotFoundError(f"Query file not found at: {query_path}")

        with open(query_path, 'r') as f:
            sql = f.read()

        logger.info("Connecting to AACT database...")
        conn = self._get_connection()
        logger.info("Successfully connected to AACT.")
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                logger.info("Starting trial extraction from AACT using streaming.")
                cur.execute(sql)
                logger.info("Trial extraction query started successfully.")
                
                total_fetched = 0
                # Stream results in batches to avoid loading all records into memory
                while True:
                    rows = cur.fetchmany(size=postgres_fetch_size)
                    if not rows:
                        break

                    total_fetched += len(rows)
                    logger.info(f"Extracted {total_fetched} trials from AACT database so far.")

                    for row in rows:
                        yield dict(row)
                    
        except Exception as e:
            logger.error(f"Error during query execution: {e}")
            raise
        finally:
            if conn:
                conn.close()
            logger.info("Closed connection to AACT")

