"""Analyze chunk files for duplicate content."""
import json
import uuid
from pathlib import Path
from collections import Counter, defaultdict

chunks_dir = Path("output/pipeline/chunks")

def chunk_to_point_id(chunk_id):
    hex32 = chunk_id[:32].ljust(32, "0")
    return str(uuid.UUID(hex32))

# Load all chunks
chunks = []
for p in sorted(chunks_dir.rglob("*.json")):
    data = json.loads(p.read_text())
    chunks.append(data)

print(f"Total chunk files: {len(chunks)}")

# 1. Check duplicate chunk_ids
chunk_ids = [c["chunk_id"] for c in chunks]
print(f"Unique chunk_ids: {len(set(chunk_ids))}")

dup_cids = {k: v for k, v in Counter(chunk_ids).items() if v > 1}
if dup_cids:
    print(f"\n=== Duplicate chunk_ids: {len(dup_cids)} ===")
    for cid, cnt in list(dup_cids.items())[:3]:
        print(f"  {cid[:32]}... x{cnt}")

# 2. Check duplicate point_ids
point_ids = [chunk_to_point_id(c["chunk_id"]) for c in chunks]
print(f"Unique point_ids: {len(set(point_ids))}")

# 3. Check duplicate chunk_text content
text_to_chunks = defaultdict(list)
for c in chunks:
    text = c.get("chunk_text", "")[:200]  # first 200 chars as key
    text_to_chunks[text].append(c)

dup_texts = {k: v for k, v in text_to_chunks.items() if len(v) > 1}
print(f"\nChunks with duplicate content (first 200 chars): {len(dup_texts)}")
total_dup_chunks = sum(len(v) for v in dup_texts.values())
print(f"Total chunks involved in duplicates: {total_dup_chunks}")

for text_key, dups in list(dup_texts.items())[:5]:
    print(f"\n--- Duplicate group ({len(dups)} chunks) ---")
    print(f"  Text: {text_key[:100]}...")
    for d in dups:
        print(f"  chunk_id: {d['chunk_id'][:24]}  doc_id: {d.get('doc_id','')[:24]}  "
              f"title: {d.get('doc_title','')[:40]}  pos: {d.get('chunk_position','?')}")

# 4. Check if same doc_id produced duplicate chunks at same position
pos_key_counts = Counter()
for c in chunks:
    key = (c.get("doc_id", ""), c.get("chunk_position", -1))
    pos_key_counts[key] += 1

dup_pos = {k: v for k, v in pos_key_counts.items() if v > 1}
if dup_pos:
    print(f"\n=== Same doc_id + chunk_position duplicates: {len(dup_pos)} ===")
    for (did, pos), cnt in list(dup_pos.items())[:5]:
        print(f"  doc_id: {did[:24]}  position: {pos}  count: {cnt}")

# 5. Check chunk_hash uniqueness
hashes = [c.get("chunk_hash", "") for c in chunks]
dup_hashes = {k: v for k, v in Counter(hashes).items() if v > 1 and k}
if dup_hashes:
    print(f"\n=== Duplicate chunk_hash: {len(dup_hashes)} ===")
    for h, cnt in list(dup_hashes.items())[:5]:
        print(f"  {h[:32]}... x{cnt}")
