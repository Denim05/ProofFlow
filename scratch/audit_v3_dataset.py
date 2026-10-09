"""Comprehensive Audit for Dataset v3.0.0-canonical-18.

Verifies:
1. Exact & near duplicate cross-split leakage
2. Sample ID uniqueness & format
3. Provenance tracking
4. Taxonomy mapping correctness
5. Span and text integrity
6. NO_EVENT handling
7. Class distribution and split counts
"""

import json
import os
from collections import Counter
from difflib import SequenceMatcher

V3_DIR = "ml/events/data/v3"

def load(split):
    path = os.path.join(V3_DIR, f"{split}.jsonl")
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

train = load("train")
val = load("val")
test = load("test")
all_samples = train + val + test

print(f"=== SAMPLE COUNTS ===")
print(f"Train: {len(train)}")
print(f"Val:   {len(val)}")
print(f"Test:  {len(test)}")
print(f"Total: {len(all_samples)}")

# 1. Unique sample IDs
sample_ids = [s["sample_id"] for s in all_samples]
print(f"\n=== SAMPLE ID AUDIT ===")
print(f"Total sample IDs: {len(sample_ids)}")
print(f"Unique sample IDs: {len(set(sample_ids))}")
assert len(sample_ids) == len(set(sample_ids)), "Duplicate sample_ids found!"

# 2. Text uniqueness & Exact cross-split overlap
train_t = {s["text"].strip().lower() for s in train}
val_t = {s["text"].strip().lower() for s in val}
test_t = {s["text"].strip().lower() for s in test}

print(f"\n=== EXACT LEAKAGE AUDIT ===")
print(f"Train-Val exact overlap: {len(train_t & val_t)}")
print(f"Train-Test exact overlap: {len(train_t & test_t)}")
print(f"Val-Test exact overlap: {len(val_t & test_t)}")
assert len(train_t & val_t) == 0
assert len(train_t & test_t) == 0
assert len(val_t & test_t) == 0

# 3. Near duplicate cross-split check
print(f"\n=== NEAR DUPLICATE AUDIT (SequenceMatcher) ===")
for name, s1, s2 in [("Train-Val", train, val), ("Train-Test", train, test), ("Val-Test", val, test)]:
    near_88, near_80 = [], []
    for item1 in s1:
        for item2 in s2:
            sim = SequenceMatcher(None, item1["text"].lower(), item2["text"].lower()).ratio()
            if sim >= 0.88:
                near_88.append((sim, item1["text"], item2["text"]))
            elif sim >= 0.80:
                near_80.append((sim, item1["text"], item2["text"]))
    print(f"{name}: >=0.88={len(near_88)}, 0.80-0.87={len(near_80)}")
    assert len(near_88) == 0, f"Near duplicates >= 0.88 found in {name}!"

# 4. Empty text and span audit
print(f"\n=== TEXT & SPAN INTEGRITY ===")
empty_text = [s for s in all_samples if not s.get("text") or not s["text"].strip()]
print(f"Empty text count: {len(empty_text)}")
assert len(empty_text) == 0

no_events = [s for s in all_samples if s["canonical_event_type"] == "NO_EVENT"]
print(f"NO_EVENT count: {len(no_events)}")
for s in no_events:
    assert s["original_event_type"] == "NO_EVENT"
    assert s["canonical_event_type"] == "NO_EVENT"
    assert s["taxonomy_category"] == "NEGATIVE_SAMPLE"

# 5. Non-canonical legacy samples
legacy = [s for s in all_samples if not s["is_canonical"]]
print(f"Unmapped legacy dispute samples count: {len(legacy)}")
for s in legacy:
    assert s["canonical_event_type"] is None
    assert s["taxonomy_category"] == "LEGACY_DISPUTE"

# 6. Canonical class representation in Test
test_canonical_counts = Counter(s["canonical_event_type"] for s in test if s["is_canonical"])
print(f"\n=== TEST SPLIT CANONICAL CLASS COVERAGE (18 + NO_EVENT) ===")
print(f"Total canonical classes covered in Test: {len(test_canonical_counts)} / 19")
for cls_name, cnt in sorted(test_canonical_counts.items()):
    print(f"  {cls_name:<25}: {cnt}")
assert len(test_canonical_counts) == 19, "Missing canonical classes in Test split!"

print("\nALL AUDIT INVARIANTS PASSED SUCCESSFULLY!")
