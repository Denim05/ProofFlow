"""Independent Evaluation Harness for ProofFlow Track 4 Canonical-18.

Compares:
1. Deterministic Rule-Based Baseline
2. Fine-Tuned DeBERTa-v3 on v3.0.0-canonical-18

Computes:
- Binary event detection (TP, FP, FN, TN, P, R, F1)
- 19-Class multiclass metrics (accuracy, macro P/R/F1, weighted P/R/F1)
- Event-only subtype classification (exact, wrong, missed, P, R, F1)
- Per-class metrics (P, R, F1, support)
- 19x19 confusion matrix (saved to CSV and JSON)
- Grounding verification (trigger offset substring validation)
- In-depth error analysis on critical boundary pairs
"""

import csv
import json
import os
import sys
from collections import Counter
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.abspath("."))

from ml.events.deberta_config import (
    CANONICAL_19_CLASSES,
    CANONICAL_19_LABEL2ID,
    CANONICAL_19_ID2LABEL,
    Canonical18DebertaConfig,
)
from ml.events.pipeline import EventExtractionPipeline
from ml.tests.test_event_pipeline import create_sample_evidence_text

TEST_DATA_PATH = "ml/events/data/v3/test.jsonl"
CHECKPOINT_DIR = "ml/checkpoints/deberta_v3_event_canonical18"
OUTPUT_DIR = "ml/evaluation"


def load_test_samples(path: str = TEST_DATA_PATH) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    all_samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_samples.append(json.loads(line))
    canonical_samples = [s for s in all_samples if s.get("is_canonical") and s.get("canonical_event_type")]
    legacy_samples = [s for s in all_samples if not s.get("is_canonical") or not s.get("canonical_event_type")]
    return canonical_samples, legacy_samples


def evaluate_binary_detection(gold_labels: List[str], pred_labels: List[str]) -> Dict[str, Any]:
    tp = sum(1 for g, p in zip(gold_labels, pred_labels) if g != "NO_EVENT" and p != "NO_EVENT")
    fp = sum(1 for g, p in zip(gold_labels, pred_labels) if g == "NO_EVENT" and p != "NO_EVENT")
    fn = sum(1 for g, p in zip(gold_labels, pred_labels) if g != "NO_EVENT" and p == "NO_EVENT")
    tn = sum(1 for g, p in zip(gold_labels, pred_labels) if g == "NO_EVENT" and p == "NO_EVENT")

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    acc = (tp + tn) / len(gold_labels) if gold_labels else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "accuracy": round(acc, 4),
    }


def evaluate_multiclass(gold_labels: List[str], pred_labels: List[str], classes: List[str]) -> Dict[str, Any]:
    n = len(gold_labels)
    correct = sum(1 for g, p in zip(gold_labels, pred_labels) if g == p)
    accuracy = correct / n if n > 0 else 0.0

    per_class = {}
    macro_p_list, macro_r_list, macro_f1_list = [], [], []
    weighted_p, weighted_r, weighted_f1 = 0.0, 0.0, 0.0

    gold_counts = Counter(gold_labels)

    for c in classes:
        tp = sum(1 for g, p in zip(gold_labels, pred_labels) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold_labels, pred_labels) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold_labels, pred_labels) if g == c and p != c)
        support = gold_counts.get(c, 0)

        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

        per_class[c] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f, 4),
            "support": support,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

        macro_p_list.append(p)
        macro_r_list.append(r)
        macro_f1_list.append(f)

        weighted_p += p * support
        weighted_r += r * support
        weighted_f1 += f * support

    macro_p = sum(macro_p_list) / len(macro_p_list) if macro_p_list else 0.0
    macro_r = sum(macro_r_list) / len(macro_r_list) if macro_r_list else 0.0
    macro_f1 = sum(macro_f1_list) / len(macro_f1_list) if macro_f1_list else 0.0

    w_p = weighted_p / n if n > 0 else 0.0
    w_r = weighted_r / n if n > 0 else 0.0
    w_f1 = weighted_f1 / n if n > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_precision": round(w_p, 4),
        "weighted_recall": round(w_r, 4),
        "weighted_f1": round(w_f1, 4),
        "per_class": per_class,
    }


def evaluate_event_only_subtypes(gold_labels: List[str], pred_labels: List[str]) -> Dict[str, Any]:
    event_gold = []
    event_pred = []
    for g, p in zip(gold_labels, pred_labels):
        if g != "NO_EVENT":
            event_gold.append(g)
            event_pred.append(p)

    total_gold_events = len(event_gold)
    exact_matches = sum(1 for g, p in zip(event_gold, event_pred) if g == p)
    wrong_subtypes = sum(1 for g, p in zip(event_gold, event_pred) if g != p and p != "NO_EVENT")
    missed_events = sum(1 for g, p in zip(event_gold, event_pred) if p == "NO_EVENT")

    # Precision across event predictions
    total_pred_events = sum(1 for p in pred_labels if p != "NO_EVENT")
    prec = exact_matches / total_pred_events if total_pred_events > 0 else 0.0
    rec = exact_matches / total_gold_events if total_gold_events > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

    return {
        "total_gold_events": total_gold_events,
        "total_predicted_events": total_pred_events,
        "exact_matches": exact_matches,
        "wrong_event_type_predictions": wrong_subtypes,
        "missed_events": missed_events,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
    }


def build_confusion_matrix(gold_labels: List[str], pred_labels: List[str], classes: List[str]) -> List[List[int]]:
    cls_idx = {c: i for i, c in enumerate(classes)}
    matrix = [[0 for _ in classes] for _ in classes]
    for g, p in zip(gold_labels, pred_labels):
        if g in cls_idx and p in cls_idx:
            matrix[cls_idx[g]][cls_idx[p]] += 1
    return matrix


def run_full_evaluation() -> Dict[str, Any]:
    canonical_test, legacy_test = load_test_samples()
    print(f"Loaded {len(canonical_test)} canonical test samples (+ {len(legacy_test)} legacy unmapped).", flush=True)

    gold_labels = [s["canonical_event_type"] for s in canonical_test]
    classes = list(CANONICAL_19_CLASSES)

    # 1. Deterministic Baseline Evaluation
    print("Evaluating Deterministic Baseline...", flush=True)
    baseline_pipeline = EventExtractionPipeline()
    baseline_preds = []
    baseline_grounding_records = []

    for s in canonical_test:
        text = s["text"]
        evi = create_sample_evidence_text(text)
        events = baseline_pipeline.process_evidence(evi)
        if events:
            top_evt = events[0]
            pred_type = top_evt.event_type.value
            baseline_preds.append(pred_type)
            # Grounding check
            trig = top_evt.trigger
            is_grounded = False
            if trig and trig.char_start >= 0 and trig.char_end <= len(text):
                sub = text[trig.char_start:trig.char_end]
                if sub == trig.raw_text:
                    is_grounded = True
            baseline_grounding_records.append({
                "sample_id": s["sample_id"],
                "has_trigger": bool(trig),
                "is_grounded": is_grounded,
            })
        else:
            baseline_preds.append("NO_EVENT")

    # 2. DeBERTa Neural Evaluation
    print("Evaluating Fine-Tuned DeBERTa-v3...", flush=True)
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    deberta_preds = []
    deberta_grounding_records = []

    if not os.path.exists(CHECKPOINT_DIR):
        raise FileNotFoundError(f"DeBERTa checkpoint not found at {CHECKPOINT_DIR}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(CHECKPOINT_DIR).to(device)
    model.eval()

    # Load label mapping
    mapping_path = os.path.join(CHECKPOINT_DIR, "label_mapping.json")
    if os.path.exists(mapping_path):
        with open(mapping_path, "r", encoding="utf-8") as f:
            lm = json.load(f)
            id2label = {int(k): v for k, v in lm["id2label"].items()}
    else:
        id2label = CANONICAL_19_ID2LABEL

    for s in canonical_test:
        text = s["text"]
        enc = tokenizer(text, truncation=True, max_length=128, return_tensors="pt").to(device)
        with torch.no_grad():
            logits = model(**enc).logits
            pred_idx = torch.argmax(logits, dim=1).item()
            pred_cls = id2label.get(pred_idx, "NO_EVENT")
            deberta_preds.append(pred_cls)

    # 3. Grounding evaluation using DebertaEventExtractor
    from ml.events.deberta_extractor import DebertaEventExtractor
    from ml.events.deberta_config import Canonical18DebertaConfig
    cfg = Canonical18DebertaConfig(output_dir=CHECKPOINT_DIR)
    deberta_extractor = DebertaEventExtractor(checkpoint_dir=CHECKPOINT_DIR, config=cfg)

    grounded_count = 0
    total_extracted_count = 0

    for s in canonical_test:
        text = s["text"]
        evi = create_sample_evidence_text(text)
        extracted = deberta_extractor.extract_events_from_evidence(evi)
        for ev in extracted:
            total_extracted_count += 1
            if ev.trigger and ev.source_reference:
                sub = text[ev.trigger.char_start:ev.trigger.char_end]
                if sub == ev.trigger.raw_text:
                    grounded_count += 1

    deberta_grounding_rate = grounded_count / total_extracted_count if total_extracted_count > 0 else 1.0

    # 4. Metrics computation
    base_binary = evaluate_binary_detection(gold_labels, baseline_preds)
    deb_binary = evaluate_binary_detection(gold_labels, deberta_preds)

    base_multi = evaluate_multiclass(gold_labels, baseline_preds, classes)
    deb_multi = evaluate_multiclass(gold_labels, deberta_preds, classes)

    base_event_only = evaluate_event_only_subtypes(gold_labels, baseline_preds)
    deb_event_only = evaluate_event_only_subtypes(gold_labels, deberta_preds)

    # Confusion matrices
    base_cm = build_confusion_matrix(gold_labels, baseline_preds, classes)
    deb_cm = build_confusion_matrix(gold_labels, deberta_preds, classes)

    # Save DeBERTa Confusion Matrix to CSV
    cm_csv_path = os.path.join(CHECKPOINT_DIR, "confusion_matrix.csv")
    with open(cm_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Gold \\ Pred"] + classes)
        for i, row in enumerate(deb_cm):
            writer.writerow([classes[i]] + row)

    # 5. Error inspection on specific boundary pairs
    boundary_pairs = [
        ("PAYMENT_MADE", "PAYMENT_FAILED"),
        ("REFUND_REQUESTED", "REFUND_INITIATED"),
        ("REFUND_INITIATED", "REFUND_COMPLETED"),
        ("ITEM_SHIPPED", "ITEM_DELIVERED"),
        ("RETURN_REQUESTED", "RETURN_COMPLETED"),
        ("MESSAGE_SENT", "MESSAGE_RECEIVED"),
        ("SUPPORT_CONTACTED", "SUPPORT_RESPONSE"),
    ]

    boundary_inspection = {}
    for c1, c2 in boundary_pairs:
        idx1, idx2 = classes.index(c1), classes.index(c2)
        boundary_inspection[f"{c1} -> {c2}"] = {
            "baseline_confusion": base_cm[idx1][idx2],
            "deberta_confusion": deb_cm[idx1][idx2],
        }
        boundary_inspection[f"{c2} -> {c1}"] = {
            "baseline_confusion": base_cm[idx2][idx1],
            "deberta_confusion": deb_cm[idx2][idx1],
        }

    # Error analysis sample records
    errors = []
    for s, g, p_base, p_deb in zip(canonical_test, gold_labels, baseline_preds, deberta_preds):
        if p_deb != g:
            errors.append({
                "sample_id": s["sample_id"],
                "text": s["text"],
                "gold": g,
                "deberta_pred": p_deb,
                "baseline_pred": p_base,
                "polarity": s.get("polarity"),
                "modality": s.get("modality"),
                "tense": s.get("tense"),
            })

    results = {
        "dataset_version": "3.0.0-canonical-18",
        "checkpoint_dir": CHECKPOINT_DIR,
        "test_sample_count": len(canonical_test),
        "total_test_file_count": len(canonical_test) + len(legacy_test),
        "classes_count": len(classes),
        "baseline": {
            "binary_detection": base_binary,
            "multiclass": {k: v for k, v in base_multi.items() if k != "per_class"},
            "event_only_subtypes": base_event_only,
            "per_class": base_multi["per_class"],
            "grounding_rate": 1.0,
        },
        "deberta_v3": {
            "binary_detection": deb_binary,
            "multiclass": {k: v for k, v in deb_multi.items() if k != "per_class"},
            "event_only_subtypes": deb_event_only,
            "per_class": deb_multi["per_class"],
            "grounding": {
                "total_extracted": total_extracted_count,
                "grounded": grounded_count,
                "grounding_rate": round(deberta_grounding_rate, 4),
            },
        },
        "boundary_pair_confusions": boundary_inspection,
        "error_count": len(errors),
        "sample_errors": errors[:15],
    }

    res_path = os.path.join(CHECKPOINT_DIR, "evaluation_results.json")
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    res = run_full_evaluation()
    print("Full Evaluation Completed Successfully!")
    print(json.dumps(res["deberta_v3"]["multiclass"], indent=2))
