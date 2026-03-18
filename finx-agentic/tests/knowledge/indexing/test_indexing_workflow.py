import asyncio

from src.knowledge.indexing.schema_metadata import SchemaMetadataWorkflow, build_episode


def test_build_episode_accepts_dynamic_source_payload() -> None:
    payload = {
        "name": "transactions",
        "database": "dw",
        "description": "Raw transaction ledger",
        "domain": "payments",
        "columns": [
            {
                "name": "transaction_id",
                "data_type": "string",
                "description": "Primary transaction identifier",
            },
            {
                "name": "amount",
                "data_type": "decimal",
                "description": "Settled amount",
            },
        ],
        "relationships": [
            {
                "source_table": "transactions",
                "target_table": "accounts",
                "relationship_type": "join",
                "source_column": "account_id",
                "target_column": "account_id",
            }
        ],
    }

    episode = build_episode(payload, index=0)
    body = episode["body"]
    metadata = body["metadata"]
    blocks = {block["name"]: block["content"] for block in body["context_blocks"]}

    assert episode["name"] == "transactions"
    assert metadata == {}
    assert "TABLE_PROFILE" in blocks
    assert "COLUMN_CATALOG" in blocks
    assert "RELATIONSHIP_HINTS" in blocks
    assert "full_name=dw.transactions" in blocks["TABLE_PROFILE"]
    assert "type=join" in blocks["RELATIONSHIP_HINTS"]


def test_build_episode_accepts_advanced_context_block_string() -> None:
    payload = {
        "name": "customer_profile_context",
        "body": {
            "context_block": (
                "<FACTS>\ncustomer uses premium card\n</FACTS>"
                "<ENTITIES>\nCustomer(id, segment)\n</ENTITIES>"
                "<USER_SUMMARY>\nPrefers monthly reports\n</USER_SUMMARY>"
            ),
            "metadata": {"source": "zep"},
        },
    }

    episode = build_episode(payload, index=0)
    body = episode["body"]
    blocks = {block["name"]: block["content"] for block in body["context_blocks"]}

    assert episode["name"] == "customer_profile_context"
    assert body["metadata"] == {"source": "zep"}
    assert blocks["FACTS"] == "customer uses premium card"
    assert blocks["ENTITIES"] == "Customer(id, segment)"
    assert blocks["USER_SUMMARY"] == "Prefers monthly reports"


def test_build_episode_accepts_advanced_context_map() -> None:
    payload = {
        "name": "payments_context",
        "body": {
            "facts": ["transaction joins account by account_id"],
            "entity_results": ["Table: transactions", "Table: accounts"],
            "user_summary": {"timezone": "Asia/Ho_Chi_Minh"},
        },
    }

    episode = build_episode(payload, index=0)
    body = episode["body"]
    blocks = {block["name"]: block["content"] for block in body["context_blocks"]}

    assert "FACTS" in blocks
    assert "ENTITIES" in blocks
    assert "USER_SUMMARY" in blocks


def test_build_episode_preserves_explicit_entities_relationships_payload() -> None:
    payload = {
        "name": "explicit_payload",
        "body": {
            "entities": [{"type": "Table", "attributes": {"table_name": "dw.transactions"}}],
            "relationships": [
                {
                    "type": "COMMONLY_JOINED_WITH",
                    "source": "dw.transactions",
                    "target": "dw.accounts",
                }
            ],
        },
    }

    episode = build_episode(payload, index=0)
    body = episode["body"]

    assert "entities" in body
    assert "relationships" in body
    assert "context_blocks" not in body


class _Snapshot:
    def model_dump(self) -> dict:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "embedding_tokens": 0,
            "llm_calls": 0,
            "embedding_calls": 0,
            "cost_usd": 0.0,
            "breakdown": {},
        }


class _Tracker:
    def __init__(self) -> None:
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1

    def snapshot(self) -> _Snapshot:
        return _Snapshot()


class _DummyGraph:
    def __init__(self, *, fail_bulk: bool = False) -> None:
        self.cost_tracker = _Tracker()
        self._fail_bulk = fail_bulk
        self.bulk_calls = 0
        self.single_calls = 0

    async def write_episodes_bulk(self, episodes: list[dict], saga: str) -> dict[str, int]:
        self.bulk_calls += 1
        if self._fail_bulk:
            raise RuntimeError("bulk failed")
        return {"nodes": len(episodes), "edges": len(episodes)}

    async def write_episode(
        self,
        name: str,
        body: dict,
        source_description: str,
        saga: str,
    ) -> dict[str, int]:
        self.single_calls += 1
        return {"nodes": 1, "edges": 1}

    async def count_nodes(self, label: str) -> int:
        return 0

    async def count_edges(self) -> int:
        return 0

    async def get_node_names(self, label: str) -> set[str]:
        return set()


def test_index_items_uses_multi_step_workflow_and_returns_summary() -> None:
    workflow = SchemaMetadataWorkflow(graph=_DummyGraph())
    result = asyncio.run(
        workflow.index_items([
            {"name": "transactions", "content": "sample context"},
        ])
    )

    assert "step_results" in result
    assert len(result["step_results"]) == 1

    summary = result["step_results"][0]
    assert summary["items_processed"] == 1
    assert summary["items_failed"] == 0
    assert summary["episodes_written"] == 1


def test_index_items_falls_back_to_single_writes_when_bulk_fails() -> None:
    graph = _DummyGraph(fail_bulk=True)
    workflow = SchemaMetadataWorkflow(graph=graph)

    result = asyncio.run(
        workflow.index_items([
            {"name": "accounts", "content": "sample context"},
        ])
    )

    assert graph.bulk_calls == 1
    assert graph.single_calls == 1
    assert result["step_results"][0]["items_processed"] == 1
