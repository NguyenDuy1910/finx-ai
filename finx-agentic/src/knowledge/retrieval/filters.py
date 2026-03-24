"""Build Qdrant filter conditions from RetrievalContext and business filters."""

from __future__ import annotations

from typing import Any

from qdrant_client import models


def build_qdrant_filter(
    acl_filter: dict[str, Any],
) -> models.Filter:
    """Convert a nested ACL filter dict into a Qdrant Filter.

    The input dict comes from ``RetrievalContext.to_acl_filter()`` and uses
    operators like ``$in``, ``$overlap``, ``$or``, plus plain key=value pairs.
    """
    must: list[models.Condition] = []
    should: list[models.Condition] = []

    for key, value in acl_filter.items():
        if key == "$or":
            for clause in value:
                should.append(_dict_to_condition(clause))
            continue

        if isinstance(value, bool):
            must.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
            )
        elif isinstance(value, dict):
            must.append(_operator_condition(key, value))
        else:
            must.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
            )

    return models.Filter(
        must=must or None,
        should=should or None,
    )


def build_doc_scope_filter(
    *,
    doc_id: str | None = None,
    section_id: str | None = None,
    chunk_kinds: list[str] | None = None,
    position_range: tuple[int, int] | None = None,
) -> models.Filter:
    """Build a Qdrant filter for document-scoped queries (expansion, siblings)."""
    conditions: list[models.Condition] = []

    if doc_id:
        conditions.append(
            models.FieldCondition(
                key="doc_id",
                match=models.MatchValue(value=doc_id),
            )
        )
    if section_id:
        conditions.append(
            models.FieldCondition(
                key="section_id",
                match=models.MatchValue(value=section_id),
            )
        )
    if chunk_kinds:
        conditions.append(
            models.FieldCondition(
                key="chunk_kind",
                match=models.MatchAny(any=chunk_kinds),
            )
        )
    if position_range:
        conditions.append(
            models.FieldCondition(
                key="chunk_position",
                range=models.Range(
                    gte=position_range[0],
                    lte=position_range[1],
                ),
            )
        )

    return models.Filter(must=conditions or None)


def build_search_params_filter(params: Any) -> models.Filter | None:
    """Build a Qdrant filter from a ``SearchParams`` instance.

    Filters applied (all optional, combined with AND):
      • ``source_type`` → ``source_system`` field exact match
      • ``space_key``   → ``space_key`` field exact match
    Returns ``None`` when no filtering criteria are set.
    """
    conditions: list[models.Condition] = []

    if params.source_type:
        conditions.append(
            models.FieldCondition(
                key="source_system",
                match=models.MatchValue(value=params.source_type.lower()),
            )
        )
    if params.space_key:
        conditions.append(
            models.FieldCondition(
                key="space_key",
                match=models.MatchValue(value=params.space_key),
            )
        )

    if not conditions:
        return None
    return models.Filter(must=conditions)


# ── private helpers ──────────────────────────────────────────────────────


def _operator_condition(key: str, ops: dict[str, Any]) -> models.Condition:
    """Convert ``{"$in": [...]}`` or ``{"$overlap": [...]}`` style dicts."""
    if "$in" in ops:
        return models.FieldCondition(
            key=key,
            match=models.MatchAny(any=ops["$in"]),
        )
    if "$overlap" in ops:
        return models.FieldCondition(
            key=key,
            match=models.MatchAny(any=ops["$overlap"]),
        )
    if "gte" in ops or "lte" in ops:
        return models.FieldCondition(
            key=key,
            range=models.Range(
                gte=ops.get("gte"),
                lte=ops.get("lte"),
            ),
        )
    # fallback: treat as exact match on first value
    first_val = next(iter(ops.values()), None)
    return models.FieldCondition(
        key=key,
        match=models.MatchValue(value=first_val),
    )


def _dict_to_condition(clause: dict[str, Any]) -> models.Condition:
    """Convert a single $or clause dict into a Filter (must-all)."""
    conditions: list[models.Condition] = []
    for key, value in clause.items():
        if isinstance(value, bool):
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
            )
        elif isinstance(value, dict):
            conditions.append(_operator_condition(key, value))
        else:
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
            )

    if len(conditions) == 1:
        return conditions[0]
    return models.Filter(must=conditions)
