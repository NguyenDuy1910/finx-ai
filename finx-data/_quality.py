"""Analyze quality of all canonical documents."""
import json
from pathlib import Path

for p in sorted(Path("output/pipeline").glob("*.json")):
    d = json.loads(p.read_text())
    blocks = d.get("content_blocks", [])
    title = d.get("title", "")[:50]
    sct = d.get("source_content_type", "")
    qs = d.get("metadata", {}).get("quality_score", "?")

    text_blocks = [b for b in blocks if b.get("block_type") == "text" and len(b.get("content", "")) > 10]
    table_blocks = [b for b in blocks if b.get("block_type") == "table"]
    empty_tables = [t for t in table_blocks if len(t.get("rows", [])) == 0]
    total_rows = sum(len(t.get("rows", [])) for t in table_blocks)

    full = " ".join(b.get("content", "") + b.get("markdown", "") for b in blocks)
    wc = len(full.split())

    print(
        f"{p.name:30s}  type={sct:12s}  blocks={len(blocks):3d}  "
        f"text={len(text_blocks):2d}  tables={len(table_blocks):3d}  "
        f"empty_tbl={len(empty_tables):3d}  rows={total_rows:5d}  "
        f"words={wc:6d}  qs={qs}  {title}"
    )
