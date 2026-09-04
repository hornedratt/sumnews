"""Create the sumnews database schema (``create_all``). Run: ``make db-init``."""

import asyncio

from sumnews.database.engine import dispose_engine, init_models
from sumnews.loggers import configure_logging, logger


async def main() -> None:
    configure_logging()
    await init_models()
    await dispose_engine()
    logger.info("db_init | schema=created")


if __name__ == "__main__":
    asyncio.run(main())
