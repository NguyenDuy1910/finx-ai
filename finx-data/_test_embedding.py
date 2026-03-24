"""Load real chunk JSONs and show dense / sparse embedding texts."""
import json
from pipeline.schemas.chunk import ChunkDocument
from pipeline.ingest.payload import chunk_to_embedding_texts

FILES = [
    "output/pipeline/chunks/713626942_.ListBug/chunks/intro_000.json",
    "output/pipeline/chunks/att906952724_GTGT_TECHSPEC_BILLPAYMENT_VNTOPUP_JSON.pdf/chunks/table_schema_034.json",
    "output/pipeline/chunks/att906952724_GTGT_TECHSPEC_BILLPAYMENT_VNTOPUP_JSON.pdf/chunks/section_002.json",
]

for f in FILES:
    with open(f) as fh:
        data = json.load(fh)
    chunk = ChunkDocument(**data)
    dense, sparse = chunk_to_embedding_texts(chunk)
    kind = chunk.chunk_kind.value

    print("=" * 80)
    print(f"FILE: {f.split('/chunks/')[-1]}")
    print(f"KIND: {kind}   TITLE: {chunk.doc_title[:60]}")
    print(f"HEADING: {chunk.heading[:80] if chunk.heading else '(none)'}")
    kw = chunk.keywords[:5] if chunk.keywords else "(none)"
    print(f"KEYWORDS: {kw}")
    print(f"ACRONYMS: {chunk.acronym_expansions}")
    th = chunk.table_headers[:5] if chunk.table_headers else "(none)"
    print(f"TABLE_HEADERS: {th}")

    print("-" * 35 + " DENSE " + "-" * 38)
    print(dense[:800])
    if len(dense) > 800:
        print(f"  ... [{len(dense)} chars total]")
    print(f"  >> Dense chars: {len(dense)}   est tokens: ~{len(dense) // 3}")

    print("-" * 35 + " SPARSE " + "-" * 37)
    print(sparse[:800])
    if len(sparse) > 800:
        print(f"  ... [{len(sparse)} chars total]")
    print(f"  >> Sparse chars: {len(sparse)}   est tokens: ~{len(sparse) // 3}")
    print()
