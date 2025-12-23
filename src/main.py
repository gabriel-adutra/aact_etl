import json
import logging
import sys
import os

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.db.aact_client import AACTClient
from src.processing.data_cleaner import DataCleaner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_pipeline_dry_run(limit=1000, output_file='processed_data.json'):
    """
    Orchestrates Extract -> Transform -> Load (to File).
    """
    logger.info("Starting Pipeline Dry Run...")
    
    # 1. Initialize Components
    client = AACTClient()
    cleaner = DataCleaner()
    
    processed_records = []
    
    try:
        # 2. Extract
        logger.info("Step 1: Extracting data from AACT...")
        raw_trials = client.fetch_trials()
        
        # 3. Transform
        logger.info("Step 2: Transforming and Cleaning data...")
        count = 0
        for raw_trial in raw_trials:
            count += 1
            if count > limit:
                break
                
            clean_trial = cleaner.clean_study(raw_trial)
            processed_records.append(clean_trial)
            
            if count % 100 == 0:
                logger.info(f"Processed {count} records...")

        # 4. Load (to Stdout for capture)
        # Using stderr for logs so stdout is pure JSON
        logger.info(f"Step 3: Outputting {len(processed_records)} records to stdout...", extra={'stream': sys.stderr})
        print(json.dumps(processed_records, indent=2))
            
        logger.info("Pipeline Dry Run Completed Successfully.")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Suppress lower level logs to keep stderr clean
    logging.getLogger('src.db.aact_client').setLevel(logging.WARNING)
    run_pipeline_dry_run()
