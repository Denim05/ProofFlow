"""Prepares Dataset v3.0.0-canonical-18 and its reproducibility manifest.

Reads existing v2 dataset splits, maps raw labels to the approved canonical 18 taxonomy,
preserves sample IDs and raw label provenance, prevents cross-split leakage, and
writes out train.jsonl, val.jsonl, test.jsonl, and dataset_manifest.json under ml/events/data/v3/.
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from typing import Any, Dict, List
from ml.events.taxonomy_mapping import (
    CANONICAL_18_EVENT_TYPES,
    TAXONOMY_MAPPINGS,
    TaxonomyLabelCategory,
    map_to_canonical,
)

OUTPUT_DIR = "ml/events/data/v3"
V2_DIR = "ml/events/data"
DATASET_VERSION = "3.0.0-canonical-18"
TAXONOMY_VERSION = "1.0.0-canonical-18"
LABEL_MAPPING_VERSION = "1.0.0"
PREPROCESSING_VERSION = "1.0.0"
SEED = 42


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: str, data: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")


def convert_split(split_name: str, raw_samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    v3_samples: List[Dict[str, Any]] = []

    for idx, s in enumerate(raw_samples):
        text = s["text"]
        raw_event_type = s["event_type"]
        rule = TAXONOMY_MAPPINGS[raw_event_type]
        canonical_event_type = rule.canonical_event_type

        # Deterministic sample ID and provenance
        sample_id = f"pf_v3_{split_name}_{idx + 1:04d}"
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

        v3_item: Dict[str, Any] = {
            "sample_id": sample_id,
            "provenance": {
                "source_dataset_version": "2.0.0-improved",
                "source_split": split_name,
                "source_index": idx,
                "text_hash": text_hash,
            },
            "text": text,
            "trigger_text": s.get("trigger_text", ""),
            "original_event_type": raw_event_type,
            "canonical_event_type": canonical_event_type,
            "taxonomy_category": rule.category.value,
            "is_canonical": rule.is_canonical,
            "polarity": s.get("polarity", "POSITIVE"),
            "modality": s.get("modality", "ASSERTED"),
            "tense": s.get("tense", "PAST"),
            "order_reference": s.get("order_reference"),
            "amount": s.get("amount"),
            "temporal": s.get("temporal"),
        }

        # Keep top-level 'event_type' for backward-compatible loaders (using canonical where mapped, or raw for legacy)
        v3_item["event_type"] = canonical_event_type if canonical_event_type is not None else raw_event_type

        v3_samples.append(v3_item)

    return v3_samples


def build_and_save_v3_dataset() -> Dict[str, Any]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    train_raw = load_jsonl(os.path.join(V2_DIR, "train.jsonl"))
    val_raw = load_jsonl(os.path.join(V2_DIR, "val.jsonl"))
    test_raw = load_jsonl(os.path.join(V2_DIR, "test.jsonl"))

    train_v3 = convert_split("train", train_raw)
    val_v3 = convert_split("val", val_raw)
    test_v3 = convert_split("test", test_raw)

    write_jsonl(os.path.join(OUTPUT_DIR, "train.jsonl"), train_v3)
    write_jsonl(os.path.join(OUTPUT_DIR, "val.jsonl"), val_v3)
    write_jsonl(os.path.join(OUTPUT_DIR, "test.jsonl"), test_v3)

    all_v3 = train_v3 + val_v3 + test_v3

    # Calculate statistics
    raw_class_counts: Dict[str, int] = {}
    canonical_class_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}

    for s in all_v3:
        raw_et = s["original_event_type"]
        can_et = s["canonical_event_type"] or "UNMAPPED_LEGACY"
        cat = s["taxonomy_category"]

        raw_class_counts[raw_et] = raw_class_counts.get(raw_et, 0) + 1
        canonical_class_counts[can_et] = canonical_class_counts.get(can_et, 0) + 1
        category_counts[cat] = category_counts.get(cat, 0) + 1

    per_split_canonical: Dict[str, Dict[str, int]] = {}
    for name, split_data in [("train", train_v3), ("val", val_v3), ("test", test_v3)]:
        counts: Dict[str, int] = {}
        for s in split_data:
            c = s["canonical_event_type"] or "UNMAPPED_LEGACY"
            counts[c] = counts.get(c, 0) + 1
        per_split_canonical[name] = counts

    # Verification of zero leakage
    train_texts = {s["text"].strip().lower() for s in train_v3}
    val_texts = {s["text"].strip().lower() for s in val_v3}
    test_texts = {s["text"].strip().lower() for s in test_v3}

    leakage_check = {
        "exact_duplicates_train_val": len(train_texts & val_texts),
        "exact_duplicates_train_test": len(train_texts & test_texts),
        "exact_duplicates_val_test": len(val_texts & test_texts),
    }

    manifest = {
        "dataset_name": "ProofFlow Canonical Event Dataset",
        "dataset_version": DATASET_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "label_mapping_version": LABEL_MAPPING_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "random_seed": SEED,
        "source_provenance": "ProofFlow v2.0.0-improved dataset (683 samples, 28 raw classes)",
        "summary": {
            "total_samples": len(all_v3),
            "canonical_and_negative_samples": sum(1 for s in all_v3 if s["is_canonical"]),
            "unmapped_legacy_dispute_samples": sum(1 for s in all_v3 if not s["is_canonical"]),
            "canonical_classes_count": len(CANONICAL_18_EVENT_TYPES),
            "total_classifier_targets": len(CANONICAL_18_EVENT_TYPES) + 1,  # 18 canonical + NO_EVENT
        },
        "split_counts": {
            "train": {
                "total": len(train_v3),
                "canonical_and_negative": sum(1 for s in train_v3 if s["is_canonical"]),
                "unmapped_legacy": sum(1 for s in train_v3 if not s["is_canonical"]),
            },
            "val": {
                "total": len(val_v3),
                "canonical_and_negative": sum(1 for s in val_v3 if s["is_canonical"]),
                "unmapped_legacy": sum(1 for s in val_v3 if not s["is_canonical"]),
            },
            "test": {
                "total": len(test_v3),
                "canonical_and_negative": sum(1 for s in test_v3 if s["is_canonical"]),
                "unmapped_legacy": sum(1 for s in test_v3 if not s["is_canonical"]),
            },
        },
        "leakage_verification": leakage_check,
        "taxonomy_categories_breakdown": category_counts,
        "canonical_classes": CANONICAL_18_EVENT_TYPES + ["NO_EVENT"],
        "canonical_class_distribution": canonical_class_counts,
        "per_split_canonical_distribution": per_split_canonical,
        "raw_class_distribution": raw_class_counts,
        "mapping_directory": {
            k: {
                "category": v.category.value,
                "canonical_event_type": v.canonical_event_type,
                "is_canonical": v.is_canonical,
                "justification": v.justification,
                "recommended_training_action": v.recommended_training_action,
            }
            for k, v in TAXONOMY_MAPPINGS.items()
        },
    }

    manifest_path = os.path.join(OUTPUT_DIR, "dataset_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


if __name__ == "__main__":
    m = build_and_save_v3_dataset()
    print("Dataset v3 successfully generated at:", OUTPUT_DIR)
    print("Total samples:", m["summary"]["total_samples"])
    print("Canonical & negative samples:", m["summary"]["canonical_and_negative_samples"])
    print("Unmapped legacy samples:", m["summary"]["unmapped_legacy_dispute_samples"])
    print("Leakage verification:", m["leakage_verification"])
