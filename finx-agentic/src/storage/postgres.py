from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from agno.db.postgres import PostgresDb

logger = logging.getLogger(__name__)

DEFAULT_DB_URL = "postgresql+psycopg://finx_user:finx_password@localhost:5432/finx_db"


def _get_db_url() -> str:
    return os.getenv("POSTGRES_URL", DEFAULT_DB_URL)


@lru_cache(maxsize=1)
def get_postgres_db(
    session_table: Optional[str] = None,
    memory_table: Optional[str] = None,
) -> PostgresDb:
    db_url = _get_db_url()
    logger.info("Initialising PostgresDb url=%s", db_url.split("@")[-1])
    return PostgresDb(
        db_url=db_url,
        session_table=session_table or "finx_sessions",
        memory_table=memory_table or "finx_memories",
    )
