"""Model Comparison Harness: Deterministic Baseline vs Fine-tuned DeBERTa-v3.

Evaluates both extractors against the held-out test set without fabrication,
measuring Precision, Recall, F1, argument extraction, nuance detection,
and source-grounding invariants.
"""

import json
import os
import sys
from typing import Any, Dict, List, Tuple

os.environ.setdefault("HF_HOME", os.path.abspath(".cache/huggingface"))

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from ml.events.config import event_config
from ml.events.deberta_config import default_deberta_config, detect_execution_device
from ml.events.detector import EventDetector
from ml.events.extractor import EventArgumentExtractor
from ml.events.pipeline import EventExtractionPipeline
from ml.schemas.event import EventType
from ml.tests.test_event_pipeline import create_sample_evidence_text


def load_test_split(test_path: str = "ml/events/data/test.jsonl") -> List[Dict[str, Any]]:
    records = []
    with open(test_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def run_model_comparison(
    test_path: str = "ml/events/data/test.jsonl",
    checkpoint_dir: str = "ml/checkpoints/deberta_v3_event",
    output_report_path: str = "ml/evaluation/model_comparison_results.json",
) -> Dict[str, Any]:
    """Runs head-to-head empirical evaluation on the held-out test split."""
    test_records = load_test_split(test_path)
    device_info = detect_execution_device()

    rule_pipeline = EventExtractionPipeline(config=event_config)

    # Check if fine-tuned DeBERTa model is available
    deberta_available = False
    deberta_extractor = None

    if os.path.exists(checkpoint_dir):
        try:
            from ml.events.deberta_extractor import DebertaEventExtractor
            deberta_extractor = DebertaEventExtractor(checkpoint_dir=checkpoint_dir)
            if deberta_extractor.model is not None:
                deberta_available = True
        except Exception as e:
            print(f"DeBERTa extractor initialization failed: {e}")
            deberta_available = False

    # Metrics collectors
    baseline_metrics = {
        "gold_events": 0,
        "predicted_events": 0,
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "correct_negation": 0,
        "total_negation_evaluated": 0,
        "correct_arguments": 0,
        "total_arguments_evaluated": 0,
        "grounded_events": 0,
        "unsupported_events": 0,
    }

    deberta_metrics = {
        "gold_events": 0,
        "predicted_events": 0,
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "correct_negation": 0,
        "total_negation_evaluated": 0,
        "correct_arguments": 0,
        "total_arguments_evaluated": 0,
        "grounded_events": 0,
        "unsupported_events": 0,
    }

    error_analysis_disagreements: List[Dict[str, Any]] = []

    for item in test_records:
        text = item["text"]
        gold_type = item["event_type"]
        is_gold_event = gold_type != "NO_EVENT"
        evi_text = create_sample_evidence_text(text)

        if is_gold_event:
            baseline_metrics["gold_events"] += 1
            if deberta_available:
                deberta_metrics["gold_events"] += 1

        # 1. Deterministic Baseline prediction
        base_events = rule_pipeline.process_evidence(evi_text)
        base_pred_type = base_events[0].event_type.value if base_events else "NO_EVENT"

        if base_events:
            baseline_metrics["predicted_events"] += len(base_events)
            for ev in base_events:
                if ev.source_reference and ev.trigger:
                    baseline_metrics["grounded_events"] += 1
                else:
                    baseline_metrics["unsupported_events"] += 1

        if base_pred_type == gold_type and is_gold_event:
            baseline_metrics["true_positives"] += 1
        elif base_pred_type != "NO_EVENT" and not is_gold_event:
            baseline_metrics["false_positives"] += 1
        elif base_pred_type != gold_type and is_gold_event:
            baseline_metrics["false_negatives"] += 1

        # Nuances on baseline
        if base_events and is_gold_event:
            ev = base_events[0]
            if item.get("polarity") == "NEGATED":
                baseline_metrics["total_negation_evaluated"] += 1
                if ev.polarity.value == "NEGATED":
                    baseline_metrics["correct_negation"] += 1
            if item.get("order_reference"):
                baseline_metrics["total_arguments_evaluated"] += 1
                if ev.order_reference == item["order_reference"]:
                    baseline_metrics["correct_arguments"] += 1

        # 2. DeBERTa-v3 prediction
        deb_pred_type = "NOT_EVALUATED"
        if deberta_available and deberta_extractor:
            deb_events = deberta_extractor.extract_events_from_evidence(evi_text)
            deb_pred_type = deb_events[0].event_type.value if deb_events else "NO_EVENT"

            if deb_events:
                deberta_metrics["predicted_events"] += len(deb_events)
                for ev in deb_events:
                    if ev.source_reference and ev.trigger:
                        deberta_metrics["grounded_events"] += 1
                    else:
                        deberta_metrics["unsupported_events"] += 1

            if deb_pred_type == gold_type and is_gold_event:
                deberta_metrics["true_positives"] += 1
            elif deb_pred_type != "NO_EVENT" and not is_gold_event:
                deberta_metrics["false_positives"] += 1
            elif deb_pred_type != gold_type and is_gold_event:
                deberta_metrics["false_negatives"] += 1

            if deb_events and is_gold_event:
                ev = deb_events[0]
                if item.get("polarity") == "NEGATED":
                    deberta_metrics["total_negation_evaluated"] += 1
                    if ev.polarity.value == "NEGATED":
                        deberta_metrics["correct_negation"] += 1
                if item.get("order_reference"):
                    deberta_metrics["total_arguments_evaluated"] += 1
                    if ev.order_reference == item["order_reference"]:
                        deberta_metrics["correct_arguments"] += 1

        # Record disagreements for error analysis
        if base_pred_type != deb_pred_type:
            error_analysis_disagreements.append({
                "sample_id": item.get("sample_id"),
                "text": text,
                "gold_type": gold_type,
                "baseline_prediction": base_pred_type,
                "deberta_prediction": deb_pred_type,
            })

    # Calculate per-class metrics & confusion matrix
    all_classes = sorted(list(set([it["event_type"] for it in test_records] + ["NO_EVENT"])))

    def compute_evaluation_views(pred_key: str):
        cm = {g: {p: 0 for p in all_classes} for g in all_classes}
        per_class = {}
        predictions = []

        for it in test_records:
            g = it["event_type"]
            evi_t = create_sample_evidence_text(it["text"])
            if pred_key == "baseline":
                evs = rule_pipeline.process_evidence(evi_t)
            else:
                evs = deberta_extractor.extract_events_from_evidence(evi_t) if deberta_available else []
            p = evs[0].event_type.value if evs else "NO_EVENT"
            cm[g][p] = cm[g].get(p, 0) + 1
            predictions.append((g, p, evs))

        # 1. Per-class metrics
        for c in all_classes:
            tp = cm[c].get(c, 0)
            fp = sum(cm[other].get(c, 0) for other in all_classes if other != c)
            fn = sum(cm[c].get(other, 0) for other in all_classes if other != c)
            support = sum(cm[c].values())
            p_val = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r_val = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1_val = (2 * p_val * r_val) / (p_val + r_val) if (p_val + r_val) > 0 else 0.0
            per_class[c] = {
                "precision": round(p_val, 4),
                "recall": round(r_val, 4),
                "f1": round(f1_val, 4),
                "support": support,
            }

        # 2. Binary event detection (Any Event vs NO_EVENT)
        bin_tp = sum(1 for g, p, _ in predictions if g != "NO_EVENT" and p != "NO_EVENT")
        bin_fp = sum(1 for g, p, _ in predictions if g == "NO_EVENT" and p != "NO_EVENT")
        bin_fn = sum(1 for g, p, _ in predictions if g != "NO_EVENT" and p == "NO_EVENT")
        bin_tn = sum(1 for g, p, _ in predictions if g == "NO_EVENT" and p == "NO_EVENT")
        bin_p = bin_tp / (bin_tp + bin_fp) if (bin_tp + bin_fp) > 0 else 0.0
        bin_r = bin_tp / (bin_tp + bin_fn) if (bin_tp + bin_fn) > 0 else 0.0
        bin_f1 = (2 * bin_p * bin_r) / (bin_p + bin_r) if (bin_p + bin_r) > 0 else 0.0
        bin_acc = (bin_tp + bin_tn) / len(predictions) if predictions else 0.0

        # 3. Multiclass 28-class overall
        mc_correct = sum(1 for g, p, _ in predictions if g == p)
        mc_acc = mc_correct / len(predictions) if predictions else 0.0
        macro_p = sum(pc["precision"] for pc in per_class.values()) / len(per_class)
        macro_r = sum(pc["recall"] for pc in per_class.values()) / len(per_class)
        macro_f1 = sum(pc["f1"] for pc in per_class.values()) / len(per_class)

        # 4. Event-Only Multiclass (on 90 gold events)
        ev_gold = [t for t in predictions if t[0] != "NO_EVENT"]
        ev_exact = sum(1 for g, p, _ in ev_gold if g == p)
        ev_predicted_events = sum(1 for _, p, _ in ev_gold if p != "NO_EVENT")
        ev_p = ev_exact / ev_predicted_events if ev_predicted_events > 0 else 0.0
        ev_r = ev_exact / len(ev_gold) if ev_gold else 0.0
        ev_f1 = (2 * ev_p * ev_r) / (ev_p + ev_r) if (ev_p + ev_r) > 0 else 0.0

        # 5. Quality, Grounding, and Nuance
        all_predicted_evs = [ev for _, _, ev_list in predictions for ev in ev_list]
        grounded = sum(1 for ev in all_predicted_evs if ev.source_reference and ev.trigger)
        unsupported = len(all_predicted_evs) - grounded
        grounding_rate = grounded / len(all_predicted_evs) if all_predicted_evs else 1.0
        unsupported_rate = unsupported / len(all_predicted_evs) if all_predicted_evs else 0.0

        neg_total = sum(1 for it in test_records if it.get("polarity") == "NEGATED")
        neg_correct = 0
        for it in test_records:
            if it.get("polarity") == "NEGATED":
                evi_t = create_sample_evidence_text(it["text"])
                if pred_key == "baseline":
                    evs = rule_pipeline.process_evidence(evi_t)
                else:
                    evs = deberta_extractor.extract_events_from_evidence(evi_t) if deberta_available else []
                if evs and evs[0].polarity.value == "NEGATED":
                    neg_correct += 1
        neg_acc = neg_correct / neg_total if neg_total > 0 else 1.0

        return {
            "summary": {
                "precision": round(ev_p, 4),
                "recall": round(ev_r, 4),
                "f1": round(ev_f1, 4),
                "true_positives": ev_exact,
                "false_positives": ev_predicted_events - ev_exact,
                "false_negatives": len(ev_gold) - ev_exact,
                "total_predicted": len(all_predicted_evs),
                "grounding_rate": round(grounding_rate, 4),
                "unsupported_rate": round(unsupported_rate, 4),
                "negation_accuracy": round(neg_acc, 4),
            },
            "binary_event_detection": {
                "tp": bin_tp,
                "fp": bin_fp,
                "fn": bin_fn,
                "tn": bin_tn,
                "accuracy": round(bin_acc, 4),
                "precision": round(bin_p, 4),
                "recall": round(bin_r, 4),
                "f1": round(bin_f1, 4),
            },
            "multiclass_28_class": {
                "accuracy": round(mc_acc, 4),
                "micro_f1": round(mc_acc, 4),
                "macro_precision": round(macro_p, 4),
                "macro_recall": round(macro_r, 4),
                "macro_f1": round(macro_f1, 4),
            },
            "event_only_multiclass": {
                "gold_events": len(ev_gold),
                "exact_type_matches": ev_exact,
                "wrong_type_predicted": ev_predicted_events - ev_exact,
                "missed_as_no_event": len(ev_gold) - ev_predicted_events,
                "precision": round(ev_p, 4),
                "recall": round(ev_r, 4),
                "f1": round(ev_f1, 4),
            },
            "per_class": per_class,
            "confusion_matrix": cm,
        }

    base_eval = compute_evaluation_views("baseline")
    deb_eval = compute_evaluation_views("deberta") if deberta_available else None

    comparison_report = {
        "evaluation_name": "ProofFlow ML Track 4 Held-Out Test Evaluation (Audited)",
        "dataset_path": test_path,
        "test_sample_count": len(test_records),
        "device_info": device_info,
        "deberta_status": "EVALUATED" if deberta_available else "NOT_TRAINED",
        "deterministic_baseline": base_eval["summary"],
        "baseline_binary_detection": base_eval["binary_event_detection"],
        "baseline_multiclass_28_class": base_eval["multiclass_28_class"],
        "baseline_per_class": base_eval["per_class"],
        "baseline_confusion_matrix": base_eval["confusion_matrix"],
        "finetuned_deberta_v3": deb_eval["summary"] if deb_eval else "NOT_EVALUATED",
        "deberta_binary_detection": deb_eval["binary_event_detection"] if deb_eval else {},
        "deberta_multiclass_28_class": deb_eval["multiclass_28_class"] if deb_eval else {},
        "deberta_event_only_multiclass": deb_eval["event_only_multiclass"] if deb_eval else {},
        "deberta_per_class": deb_eval["per_class"] if deb_eval else {},
        "deberta_confusion_matrix": deb_eval["confusion_matrix"] if deb_eval else {},
        "disagreements_count": len(error_analysis_disagreements),
        "disagreements_sample": error_analysis_disagreements[:15],
    }

    os.makedirs(os.path.dirname(output_report_path), exist_ok=True)
    with open(output_report_path, "w", encoding="utf-8") as f:
        json.dump(comparison_report, f, indent=2)

    return comparison_report


if __name__ == "__main__":
    report = run_model_comparison()
    print(json.dumps(report, indent=2))
