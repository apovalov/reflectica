"""Initialize MinIO bucket on startup."""
import os
import time

from app.storage.minio_client import MinIOClient
from app.utils.logging import logger


def init_minio():
    """Initialize MinIO bucket."""
    max_retries = 10
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            storage = MinIOClient()
            logger.info("MinIO bucket initialized successfully")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"MinIO initialization failed (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                logger.error(f"MinIO initialization failed after {max_retries} attempts: {e}")
                raise


if __name__ == "__main__":
    init_minio()

