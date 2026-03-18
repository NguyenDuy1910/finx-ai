from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.knowledge.graph.falkordb_impl import (
    FalkorDbImpl,
    KnowledgeGraph,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@dataclass
class _FalkorDBConfig:
    host: str = "localhost"
    port: int = 6379


@dataclass
class _AppConfig:
    falkordb: _FalkorDBConfig = field(default_factory=_FalkorDBConfig)
    max_graph_nodes: int = 1000


def _make_result(rows: list[list[Any]]) -> MagicMock:
    r = MagicMock()
    r.result_set = rows
    return r


def _empty() -> MagicMock:
    return _make_result([])


@pytest.fixture
def impl() -> FalkorDbImpl:
    cfg = _AppConfig()
    with patch("src.knowledge.graph.falkordb_impl.FalkorDBClient", autospec=True):
        inst = FalkorDbImpl(namespace="test_graph", global_config=cfg, embedding_func=None, workspace="test")
        inst._client = MagicMock()
    return inst


# ── initialize / finalize ─────────────────────────────────────────────────────


def test_initialize_creates_indexes(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.initialize())
    assert impl._client.execute.call_count == 2


def test_initialize_tolerates_index_errors(impl: FalkorDbImpl) -> None:
    impl._client.execute.side_effect = Exception("already exists")
    run(impl.initialize())


def test_finalize_closes_client(impl: FalkorDbImpl) -> None:
    run(impl.finalize())
    impl._client.close.assert_called_once()


# ── is_empty ──────────────────────────────────────────────────────────────────


def test_is_empty_true(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[0]])
    assert run(impl.is_empty()) is True


def test_is_empty_false(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[5]])
    assert run(impl.is_empty()) is False


def test_is_empty_no_rows(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    assert run(impl.is_empty()) is True


# ── has_node ──────────────────────────────────────────────────────────────────


def test_has_node_true(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[True]])
    assert run(impl.has_node("A")) is True


def test_has_node_false(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[False]])
    assert run(impl.has_node("A")) is False


# ── get_node ──────────────────────────────────────────────────────────────────


def test_get_node_found(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[{"entity_id": "A", "name": "Alpha"}]])
    result = run(impl.get_node("A"))
    assert result == {"entity_id": "A", "name": "Alpha"}


def test_get_node_not_found(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    assert run(impl.get_node("A")) is None


def test_get_node_multiple_warns(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [[{"entity_id": "A"}], [{"entity_id": "A2"}]]
    )
    result = run(impl.get_node("A"))
    assert result == {"entity_id": "A"}


# ── get_nodes_batch ───────────────────────────────────────────────────────────


def test_get_nodes_batch(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [["A", {"entity_id": "A"}], ["B", {"entity_id": "B"}]]
    )
    result = run(impl.get_nodes_batch(["A", "B"]))
    assert result == {"A": {"entity_id": "A"}, "B": {"entity_id": "B"}}


def test_get_nodes_batch_empty(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    assert run(impl.get_nodes_batch([])) == {}


# ── upsert_node ───────────────────────────────────────────────────────────────


def test_upsert_node(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.upsert_node("A", {"entity_type": "Table", "desc": "test"}))
    impl._client.execute.assert_called_once()
    call_args = impl._client.execute.call_args
    query, params = call_args.args
    assert "MERGE" in query
    assert params["id"] == "A"


def test_upsert_node_sanitizes_entity_type(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.upsert_node("A", {"entity_type": "Table,Column", "x": 1}))
    _, params = impl._client.execute.call_args.args
    assert params["props"]["entity_type"] == "Table"


def test_upsert_node_backtick_sanitized(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.upsert_node("A", {"entity_type": "`Bad`"}))
    _, params = impl._client.execute.call_args.args
    assert "`" not in params["props"]["entity_type"]


def test_upsert_node_empty_entity_type_defaults(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.upsert_node("A", {"entity_type": ""}))
    _, params = impl._client.execute.call_args.args
    assert params["props"]["entity_type"] == "UNKNOWN"


# ── delete_node ───────────────────────────────────────────────────────────────


def test_delete_node(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.delete_node("A"))
    query = impl._client.execute.call_args[0][0]
    assert "DETACH DELETE" in query


# ── remove_nodes ──────────────────────────────────────────────────────────────


def test_remove_nodes(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.remove_nodes(["A", "B", "C"]))
    assert impl._client.execute.call_count == 3


# ── BaseKVStorage abstract methods ────────────────────────────────────────────


def test_get_by_id_delegates_to_get_node(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[{"entity_id": "A"}]])
    result = run(impl.get_by_id("A"))
    assert result == {"entity_id": "A"}


def test_get_by_ids(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [["A", {"entity_id": "A"}], ["B", {"entity_id": "B"}]]
    )
    result = run(impl.get_by_ids(["A", "B"]))
    assert len(result) == 2


def test_filter_keys_returns_missing(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([["A"]])
    missing = run(impl.filter_keys({"A", "B", "C"}))
    assert missing == {"B", "C"}


def test_filter_keys_empty_input(impl: FalkorDbImpl) -> None:
    result = run(impl.filter_keys(set()))
    assert result == set()


def test_upsert_abstract(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.upsert({"A": {"entity_type": "Table"}, "B": {"entity_type": "Column"}}))
    assert impl._client.execute.call_count == 2


def test_delete_abstract(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.delete(["A", "B"]))
    assert impl._client.execute.call_count == 2


# ── get_all_nodes / get_all_labels ────────────────────────────────────────────


def test_get_all_nodes(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [[{"entity_id": "A"}], [{"entity_id": "B"}]]
    )
    nodes = run(impl.get_all_nodes())
    assert len(nodes) == 2
    assert nodes[0]["id"] == "A"


def test_get_all_labels(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([["A"], ["B"]])
    labels = run(impl.get_all_labels())
    assert labels == ["A", "B"]


# ── get_popular_labels ────────────────────────────────────────────────────────


def test_get_popular_labels(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([["X"], ["Y"]])
    labels = run(impl.get_popular_labels(limit=10))
    assert labels == ["X", "Y"]


# ── search_labels ─────────────────────────────────────────────────────────────


def test_search_labels_fulltext_hit(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([["ACCOUNT"], ["ACCOUNT_TYPE"]])
    result = run(impl.search_labels("account"))
    assert "ACCOUNT" in result


def test_search_labels_empty_query(impl: FalkorDbImpl) -> None:
    result = run(impl.search_labels("  "))
    assert result == []


def test_search_labels_fulltext_fallback(impl: FalkorDbImpl) -> None:
    def side_effect(query, params=None):
        if "db.idx" in query:
            raise Exception("index not available")
        return _make_result([["ACCOUNT"]])

    impl._client.execute.side_effect = side_effect
    result = run(impl.search_labels("account"))
    assert result == ["ACCOUNT"]


# ── node_degree ───────────────────────────────────────────────────────────────


def test_node_degree(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[3]])
    assert run(impl.node_degree("A")) == 3


def test_node_degree_no_rows(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    assert run(impl.node_degree("A")) == 0


# ── node_degrees_batch ────────────────────────────────────────────────────────


def test_node_degrees_batch(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([["A", 2], ["B", 5]])
    result = run(impl.node_degrees_batch(["A", "B", "C"]))
    assert result["A"] == 2
    assert result["B"] == 5
    assert result["C"] == 0


# ── edge_degree / edge_degrees_batch ─────────────────────────────────────────


def test_edge_degree(impl: FalkorDbImpl) -> None:
    impl._client.execute.side_effect = [_make_result([[3]]), _make_result([[4]])]
    assert run(impl.edge_degree("A", "B")) == 7


def test_edge_degrees_batch(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([["A", 2], ["B", 3]])
    result = run(impl.edge_degrees_batch([("A", "B")]))
    assert result[("A", "B")] == 5


# ── has_edge ──────────────────────────────────────────────────────────────────


def test_has_edge_true(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[True]])
    assert run(impl.has_edge("A", "B")) is True


def test_has_edge_false(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[False]])
    assert run(impl.has_edge("A", "B")) is False


# ── get_edge ──────────────────────────────────────────────────────────────────


def test_get_edge_found(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [[{"weight": 0.9, "description": "linked"}]]
    )
    result = run(impl.get_edge("A", "B"))
    assert result is not None
    assert result["weight"] == 0.9
    assert "source_id" in result


def test_get_edge_not_found(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    assert run(impl.get_edge("A", "B")) is None


def test_get_edge_defaults_populated(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result([[{}]])
    result = run(impl.get_edge("A", "B"))
    assert result["weight"] == 1.0
    assert result["source_id"] is None
    assert result["description"] is None
    assert result["keywords"] is None


# ── get_edges_batch ───────────────────────────────────────────────────────────


def test_get_edges_batch(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [["A", "B", [{"weight": 1.0}]]]
    )
    result = run(impl.get_edges_batch([{"src": "A", "tgt": "B"}]))
    assert ("A", "B") in result


# ── get_node_edges ────────────────────────────────────────────────────────────


def test_get_node_edges(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [["A", "B"], ["A", "C"], ["A", None]]
    )
    result = run(impl.get_node_edges("A"))
    assert ("A", "B") in result
    assert ("A", "C") in result
    assert len(result) == 2


# ── get_nodes_edges_batch ─────────────────────────────────────────────────────


def test_get_nodes_edges_batch(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [["A", "A", "B", "A"], ["A", "A", "C", "C"]]
    )
    result = run(impl.get_nodes_edges_batch(["A"]))
    assert len(result["A"]) == 2


# ── upsert_edge ───────────────────────────────────────────────────────────────


def test_upsert_edge(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.upsert_edge("A", "B", {"weight": 1.0}))
    query = impl._client.execute.call_args[0][0]
    assert "MERGE" in query
    assert "DIRECTED" in query


# ── remove_edges ──────────────────────────────────────────────────────────────


def test_remove_edges(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    run(impl.remove_edges([("A", "B"), ("B", "C")]))
    assert impl._client.execute.call_count == 2


# ── get_all_edges ─────────────────────────────────────────────────────────────


def test_get_all_edges(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _make_result(
        [["A", "B", {"weight": 1.0}]]
    )
    edges = run(impl.get_all_edges())
    assert edges[0]["source"] == "A"
    assert edges[0]["target"] == "B"


# ── drop ──────────────────────────────────────────────────────────────────────


def test_drop_success(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    result = run(impl.drop())
    assert result["status"] == "success"
    assert "test" in result["message"]


def test_drop_error(impl: FalkorDbImpl) -> None:
    impl._client.execute.side_effect = Exception("connection refused")
    result = run(impl.drop())
    assert result["status"] == "error"
    assert "connection refused" in result["message"]


# ── get_knowledge_graph ───────────────────────────────────────────────────────


def test_get_knowledge_graph_node_not_found(impl: FalkorDbImpl) -> None:
    impl._client.execute.return_value = _empty()
    result = run(impl.get_knowledge_graph("MISSING"))
    assert isinstance(result, KnowledgeGraph)
    assert result.nodes == []
    assert result.is_truncated is False


def test_get_knowledge_graph_single_node_no_edges(impl: FalkorDbImpl) -> None:
    def side_effect(query, params=None):
        if "properties(n)" in query and "entity_id: $id" in query:
            return _make_result([[{"entity_id": "A", "name": "Alpha"}]])
        return _empty()

    impl._client.execute.side_effect = side_effect
    result = run(impl.get_knowledge_graph("A", max_depth=1))
    assert len(result.nodes) == 1
    assert result.nodes[0].id == "A"
    assert result.edges == []


def test_get_knowledge_graph_with_neighbors(impl: FalkorDbImpl) -> None:
    def side_effect(query, params=None):
        if "properties(n)" in query and "entity_id: $id" in query:
            return _make_result([[{"entity_id": "A"}]])
        if "startNode(r)" in query:
            return _make_result(
                [["B", {"entity_id": "B"}, "RELATED_TO", 1, {"weight": 1.0}, "A"]]
            )
        return _empty()

    impl._client.execute.side_effect = side_effect
    result = run(impl.get_knowledge_graph("A", max_depth=1))
    assert len(result.nodes) == 2
    assert len(result.edges) == 1


def test_get_knowledge_graph_wildcard(impl: FalkorDbImpl) -> None:
    def side_effect(query, params=None):
        if "count(n) AS total" in query:
            return _make_result([[2]])
        if "degree DESC" in query:
            return _make_result(
                [["A", {"entity_id": "A"}], ["B", {"entity_id": "B"}]]
            )
        if "UNWIND $ids" in query:
            return _make_result(
                [["A", "RELATED_TO", "B", 1, {"weight": 1.0}]]
            )
        return _empty()

    impl._client.execute.side_effect = side_effect
    result = run(impl.get_knowledge_graph("*"))
    assert len(result.nodes) == 2
    assert len(result.edges) == 1
    assert result.is_truncated is False


def test_get_knowledge_graph_truncated(impl: FalkorDbImpl) -> None:
    def side_effect(query, params=None):
        if "count(n) AS total" in query:
            return _make_result([[5000]])
        if "degree DESC" in query:
            return _make_result([["A", {"entity_id": "A"}]])
        return _empty()

    impl._client.execute.side_effect = side_effect
    result = run(impl.get_knowledge_graph("*", max_nodes=10))
    assert result.is_truncated is True


# ── workspace override ────────────────────────────────────────────────────────


def test_workspace_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FALKORDB_WORKSPACE", "env_ws")
    cfg = _AppConfig()
    with patch("src.knowledge.graph.falkordb_impl.FalkorDBClient"):
        instance = FalkorDbImpl("ns", cfg, None, workspace="arg_ws")
    assert instance.workspace == "env_ws"


def test_workspace_defaults_to_base() -> None:
    cfg = _AppConfig()
    with patch("src.knowledge.graph.falkordb_impl.FalkorDBClient"):
        instance = FalkorDbImpl("ns", cfg, None, workspace=None)
    assert instance.workspace == "base"


def test_workspace_arg_used_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FALKORDB_WORKSPACE", raising=False)
    cfg = _AppConfig()
    with patch("src.knowledge.graph.falkordb_impl.FalkorDBClient"):
        instance = FalkorDbImpl("ns", cfg, None, workspace="custom")
    assert instance.workspace == "custom"
