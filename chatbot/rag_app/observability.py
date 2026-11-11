"""Application events only: never log prompts, answers, credentials or user IDs."""
import logging
import threading

_lock = threading.Lock()


def configure_logging():
    logger = logging.getLogger('rag_app')
    with _lock:
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
