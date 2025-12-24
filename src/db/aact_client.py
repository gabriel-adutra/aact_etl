import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Generator, Dict, Any
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AACTClient:
    def __init__(self):
        self.conn_params = {
            "host": os.getenv("AACT_HOST"),
            "port": os.getenv("AACT_PORT"),
            "database": os.getenv("AACT_DB"),
            "user": os.getenv("AACT_USER"),
            "password": os.getenv("AACT_PASSWORD"),
        }

        
    def _get_connection(self):
        try:
            return psycopg2.connect(**self.conn_params)
        except Exception as e:
            logger.error(f"Failed to connect to AACT Database: {e}")
            raise


    def fetch_trials(self, query_path: str = "config/extract_trials.sql") -> Generator[Dict[str, Any], None, None]:
        if not os.path.exists(query_path):
            raise FileNotFoundError(f"Query file not found at: {query_path}")

        with open(query_path, 'r') as f:
            sql = f.read()

        conn = self._get_connection()
        logger.info("Connected to AACT. Executing extraction query...")
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                
                total_fetched = 0
                while True:
                    rows = cur.fetchmany(size=500)
                    if not rows:
                        break

                    for row in rows:
                        yield dict(row)
                        
                    total_fetched += len(rows)
                    logger.info(f"Fetched {total_fetched} rows so far...")
                    
        except Exception as e:
            logger.error(f"Error during query execution: {e}")
            raise
        finally:
            if conn:
                conn.close()
            logger.info("AACT Connection closed.")

