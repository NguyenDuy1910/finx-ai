"""PostgreSQL session/memory storage backed by agno's PostgresDb."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from agno.db.postgres import PostgresDb

logger = logging.getLogger(__name__)

_DEFAULT_DB_URL = "postgresql+psycopg://finx_user:finx_password@localhost:5432/finx_db"


@lru_cache(maxsize=1)
def get_postgres_db(
    session_table: Optional[str] = None,
    memory_table: Optional[str] = None,
) -> PostgresDb:
    """Get or create a cached PostgresDb instance.

    Args:
        session_table: Table name for session storage. Default: finx_sessions.
        memory_table: Table name for memory storage. Default: finx_memories.
    """
    db_url = os.getenv("POSTGRES_URL", _DEFAULT_DB_URL)
    logger.info("Initialising PostgresDb url=%s", db_url.split("@")[-1])
    return PostgresDb(
        db_url=db_url,
        session_table=session_table or "finx_sessions",
        memory_table=memory_table or "finx_memories",
    )
