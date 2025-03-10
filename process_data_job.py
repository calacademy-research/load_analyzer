#!/usr/bin/env python3
import logging
from redis_transformer import RedisWriter
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/load_analyzer_data_processor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def process_data():
    try:
        redis_handler = RedisWriter(
            host='localhost',
            port=6379,
            db=0
        )
        redis_handler.store_data()
        logger.info("data sync completed")
    except Exception as e:
        logger.error(f"data sync failed: {str(e)}")
        raise

if __name__ == "__main__":
    process_data()