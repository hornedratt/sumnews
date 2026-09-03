"""Project logger.

Import the named logger everywhere: ``from sumnews.loggers import logger``.
Message shape is ``phase | key=value`` — identifiers go in fields, not prose.
"""

import logging

logger = logging.getLogger("sumnews")


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a single stream handler to the ``sumnews`` logger. Idempotent."""
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt="%(asctime)s %(levelname)s %(name)s | %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
