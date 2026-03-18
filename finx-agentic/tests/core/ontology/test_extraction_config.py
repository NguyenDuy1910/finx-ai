from pydantic import BaseModel

from src.core.graph.ontology.extraction_config import build_extraction_instructions


class CustomerEntity(BaseModel):
    customer_id: str = ""


class OwnsAccountEdge(BaseModel):
    relationship_strength: str = ""


def test_build_extraction_instructions_uses_runtime_ontology_types() -> None:
    instructions = build_extraction_instructions(
        entity_types={"Customer": CustomerEntity},
        edge_types={"OWNS_ACCOUNT": OwnsAccountEdge},
    )

    assert "Entity types: Customer" in instructions
    assert "Edge types: OWNS_ACCOUNT" in instructions
    assert "FACTS / RELATIONSHIPS / EDGE_RESULTS" in instructions
