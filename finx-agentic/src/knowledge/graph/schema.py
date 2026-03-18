from __future__ import annotations

import logging

from .client import FalkorDBClient
from .exceptions import SchemaSetupError
from .models import NodeLabel

logger = logging.getLogger(__name__)

# ── Fulltext index definitions ─────────────────────────────────────────────────
# (index_name, label, properties[])
_FULLTEXT_INDEXES: list[tuple[str, str, list[str]]] = [
    ("ft_entities", "Entity", ["name", "description", "synonyms"]),
]

# ── Exact indexes (range index on name for fast lookup) ────────────────────────
# FalkorDB auto-indexes on labels; we add explicit indexes for key properties.
_RANGE_INDEXES: list[tuple[str, str]] = [
    (label.value, "name") for label in NodeLabel
]


def setup_schema(client: FalkorDBClient) -> None:
    """Create fulltext + range indexes.  Idempotent — skips if already exists.

    Raises ``SchemaSetupError`` on unexpected failures.
    """
    _create_entity_label(client)
    _create_fulltext_indexes(client)
    _create_range_indexes(client)
    logger.info("Graph schema setup complete.")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _create_entity_label(client: FalkorDBClient) -> None:
    """Ensure every node we create carries an ``Entity`` super-label.

    This lets the fulltext index cover ALL node types via a single label.
    We create one dummy node and delete it to force the label into the schema,
    but only if the label doesn't exist yet.
    """
    try:
        result = client.execute(
            "MATCH (n:Entity) RETURN count(n) AS c"
        )
        count = 0
        if result.result_set:
            count = result.result_set[0][0]
        if count == 0:
            client.execute(
                "CREATE (n:Entity {_placeholder: true}) "
                "DELETE n"
            )
            logger.debug("Entity label initialised.")
    except Exception as exc:
        logger.warning("Entity label init (non-fatal): %s", exc)


def _create_fulltext_indexes(client: FalkorDBClient) -> None:
    """Create fulltext indexes for entity search.

    FalkorDB uses the ``db.idx.fulltext.createNodeIndex`` procedure:
      CALL db.idx.fulltext.createNodeIndex('Label', 'prop1', 'prop2', ...)
    """
    for idx_name, label, properties in _FULLTEXT_INDEXES:
        prop_args = ", ".join(f"'{p}'" for p in properties)
        query = f"CALL db.idx.fulltext.createNodeIndex('{label}', {prop_args})"
        try:
            client.execute(query)
            logger.info("Created fulltext index: %s on :%s(%s)", idx_name, label, ", ".join(properties))
        except Exception as exc:
            msg = str(exc).lower()
            if "already indexed" in msg or "index already exists" in msg:
                logger.debug("Fulltext index %s already exists — skipping.", idx_name)
            else:
                raise SchemaSetupError(f"Failed to create index {idx_name}: {exc}") from exc


def _create_range_indexes(client: FalkorDBClient) -> None:
    """Create range indexes on ``name`` for each node label."""
    for label, prop in _RANGE_INDEXES:
        query = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        try:
            client.execute(query)
            logger.info("Created range index: %s.%s", label, prop)
        except Exception as exc:
            msg = str(exc).lower()
            if "already exists" in msg or "already indexed" in msg:
                logger.debug("Range index %s.%s already exists — skipping.", label, prop)
            else:
                raise SchemaSetupError(
                    f"Failed to create range index {label}.{prop}: {exc}"
                ) from exc
