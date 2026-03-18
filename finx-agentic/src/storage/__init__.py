"""Storage module — database connections."""

from src.storage.postgres import get_postgres_db

__all__ = ["get_postgres_db"]
