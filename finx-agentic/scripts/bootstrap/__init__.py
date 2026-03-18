"""Bootstrap indexing pipeline for FinX knowledge graph.

Clean E2E pipeline: discover → load → deterministic upsert + LLM extract → merge → upsert.
Uses FalkorDB graph store directly (no Graphiti framework).
"""
