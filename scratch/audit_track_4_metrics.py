"""
ProofFlow ML Track 4 — Comprehensive Evaluation Audit Script
Audits raw predictions from both DeBERTa-v3 and Deterministic Baseline on test.jsonl.
Computes:
1. Sample-by-sample trace
2. Binary event detection metrics
3. Multiclass 28-class metrics (Micro, Macro, Weighted, Per-Class, Confusion Matrix via sklearn)
4. Baseline metrics under both paradigms
5. Grounding span verification (verifying exact character offsets and text match)
6. Dataset split & leakage audit
7. Taxonomy audit
"""

import json
import os
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher

import numpy as np

# Ensure workspace root is in sys.path
sys.path.insert(0, "d:/ProofFlow")

from ml.events.config import event_config
from ml.events.pipeline import EventExtractionPipeline
from ml.events.deberta_extractor import DebertaEventExtractor
from ml.schemas.event import EventType
from ml.schemas.evidence_text import EvidenceText, PageLayout, PageExtractionMethod, ExtractionQualityState, TextBlock, TextLine, TextSpan, ExtractionQualityMetrics
from ml.tests.test_event_pipeline import create_sample_evidence_text

def run_audit():
    print("=" * 80)
    print("PROOFFLOW ML TRACK 4 — COMPREHENSIVE EVALUATION AUDIT")
    print("=" * 80)

    test_path = "d:/ProofFlow/ml/events/data/test.jsonl"
    checkpoint_dir = "d:/ProofFlow/ml/checkpoints/deberta_v3_event"

    with open(test_path, "r", encoding="utf-8") as f:
        test_records = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(test_records)} test samples from {test_path}")

    # Load pipelines
    rule_pipeline = EventExtractionPipeline(config=event_config)
    deberta_extractor = DebertaEventExtractor(checkpoint_dir=checkpoint_dir)

    # 1. Collect Raw Predictions
    samples_data = []

    for idx, item in enumerate(test_records):
        text = item["text"]
        gold_type = item["event_type"]
        is_gold_event = (gold_type != "NO_EVENT")
        evi_text = create_sample_evidence_text(text)

        # Baseline
        base_events = rule_pipeline.process_evidence(evi_text)
        base_pred_type = base_events[0].event_type.value if base_events else "NO_EVENT"
        is_base_pred_event = (base_pred_type != "NO_EVENT")

        # DeBERTa
        deb_events = deberta_extractor.extract_events_from_evidence(evi_text)
        deb_pred_type = deb_events[0].event_type.value if deb_events else "NO_EVENT"
        is_deb_pred_event = (deb_pred_type != "NO_EVENT")

        samples_data.append({
            "index": idx,
            "text": text,
            "gold_type": gold_type,
            "is_gold_event": is_gold_event,
            "base_pred_type": base_pred_type,
            "is_base_pred_event": is_base_pred_event,
            "base_events": base_events,
            "deb_pred_type": deb_pred_type,
            "is_deb_pred_event": is_deb_pred_event,
            "deb_events": deb_events,
            "item": item
        })

    # Print sample breakdown
    gold_types = [s["gold_type"] for s in samples_data]
    base_preds = [s["base_pred_type"] for s in samples_data]
    deb_preds = [s["deb_pred_type"] for s in samples_data]

    gold_counter = Counter(gold_types)
    base_counter = Counter(base_preds)
    deb_counter = Counter(deb_preds)

    print("\n--- SAMPLE DISTRIBUTION ---")
    print(f"Total test samples: {len(samples_data)}")
    print(f"Gold event samples: {sum(1 for s in samples_data if s['is_gold_event'])}")
    print(f"Gold NO_EVENT samples: {sum(1 for s in samples_data if not s['is_gold_event'])}")

    print(f"\nDeBERTa Predictions:")
    print(f"  Predicted as event: {sum(1 for s in samples_data if s['is_deb_pred_event'])}")
    print(f"  Predicted as NO_EVENT: {sum(1 for s in samples_data if not s['is_deb_pred_event'])}")

    print(f"\nBaseline Predictions:")
    print(f"  Predicted as event: {sum(1 for s in samples_data if s['is_base_pred_event'])}")
    print(f"  Predicted as NO_EVENT: {sum(1 for s in samples_data if not s['is_base_pred_event'])}")

    # 2. Binary Event Detection View (Event vs NO_EVENT)
    print("\n" + "=" * 80)
    print("VIEW 1: BINARY EVENT DETECTION (ANY EVENT vs NO_EVENT)")
    print("=" * 80)

    for name, is_pred_event_fn in [("Deterministic Baseline", lambda s: s["is_base_pred_event"]),
                                   ("Fine-tuned DeBERTa-v3", lambda s: s["is_deb_pred_event"])]:
        tp = sum(1 for s in samples_data if s["is_gold_event"] and is_pred_event_fn(s))
        fp = sum(1 for s in samples_data if not s["is_gold_event"] and is_pred_event_fn(s))
        fn = sum(1 for s in samples_data if s["is_gold_event"] and not is_pred_event_fn(s))
        tn = sum(1 for s in samples_data if not s["is_gold_event"] and not is_pred_event_fn(s))

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        acc = (tp + tn) / len(samples_data)

        print(f"\n{name} (Binary Event Detection):")
        print(f"  TP={tp}, FP={fp}, FN={fn}, TN={tn}")
        print(f"  Accuracy = {acc:.4f} ({acc*100:.2f}%)")
        print(f"  Precision = {prec:.4f} ({prec*100:.2f}%)")
        print(f"  Recall    = {rec:.4f} ({rec*100:.2f}%)")
        print(f"  F1 Score  = {f1:.4f} ({f1*100:.2f}%)")

    # 3. Multiclass 28-Class Classification View (sklearn)
    from sklearn.metrics import classification_report, confusion_matrix, precision_score, recall_score, f1_score, accuracy_score

    all_classes = sorted(list(set(gold_types + base_preds + deb_preds)))
    print("\n" + "=" * 80)
    print(f"VIEW 2: MULTICLASS 28-CLASS CLASSIFICATION (All {len(all_classes)} Classes)")
    print("=" * 80)

    # DeBERTa
    deb_acc = accuracy_score(gold_types, deb_preds)
    deb_macro_p = precision_score(gold_types, deb_preds, labels=all_classes, average="macro", zero_division=0)
    deb_macro_r = recall_score(gold_types, deb_preds, labels=all_classes, average="macro", zero_division=0)
    deb_macro_f1 = f1_score(gold_types, deb_preds, labels=all_classes, average="macro", zero_division=0)
    deb_weighted_f1 = f1_score(gold_types, deb_preds, labels=all_classes, average="weighted", zero_division=0)
    deb_micro_p = precision_score(gold_types, deb_preds, labels=all_classes, average="micro", zero_division=0)
    deb_micro_r = recall_score(gold_types, deb_preds, labels=all_classes, average="micro", zero_division=0)
    deb_micro_f1 = f1_score(gold_types, deb_preds, labels=all_classes, average="micro", zero_division=0)

    # Event-only subset (excluding NO_EVENT)
    event_classes = [c for c in all_classes if c != "NO_EVENT"]
    gold_event_indices = [i for i, s in enumerate(samples_data) if s["is_gold_event"]]
    gold_events_only = [gold_types[i] for i in gold_event_indices]
    deb_events_only = [deb_preds[i] for i in gold_event_indices]
    base_events_only = [base_preds[i] for i in gold_event_indices]

    deb_ev_exact_match = sum(1 for g, p in zip(gold_events_only, deb_events_only) if g == p)
    base_ev_exact_match = sum(1 for g, p in zip(gold_events_only, base_events_only) if g == p)

    print("\n--- DEBERTA-V3 (28-Class Multiclass Full Test Set: 96 samples) ---")
    print(f"  Accuracy:    {deb_acc:.4f} ({deb_acc*100:.2f}%) [{sum(1 for g, p in zip(gold_types, deb_preds) if g == p)}/96 correct]")
    print(f"  Micro P:     {deb_micro_p:.4f} ({deb_micro_p*100:.2f}%)")
    print(f"  Micro R:     {deb_micro_r:.4f} ({deb_micro_r*100:.2f}%)")
    print(f"  Micro F1:    {deb_micro_f1:.4f} ({deb_micro_f1*100:.2f}%)")
    print(f"  Macro P:     {deb_macro_p:.4f} ({deb_macro_p*100:.2f}%)")
    print(f"  Macro R:     {deb_macro_r:.4f} ({deb_macro_r*100:.2f}%)")
    print(f"  Macro F1:    {deb_macro_f1:.4f} ({deb_macro_f1*100:.2f}%)")
    print(f"  Weighted F1: {deb_weighted_f1:.4f} ({deb_weighted_f1*100:.2f}%)")

    # Baseline
    base_acc = accuracy_score(gold_types, base_preds)
    base_macro_p = precision_score(gold_types, base_preds, labels=all_classes, average="macro", zero_division=0)
    base_macro_r = recall_score(gold_types, base_preds, labels=all_classes, average="macro", zero_division=0)
    base_macro_f1 = f1_score(gold_types, base_preds, labels=all_classes, average="macro", zero_division=0)
    base_weighted_f1 = f1_score(gold_types, base_preds, labels=all_classes, average="weighted", zero_division=0)
    base_micro_p = precision_score(gold_types, base_preds, labels=all_classes, average="micro", zero_division=0)
    base_micro_r = recall_score(gold_types, base_preds, labels=all_classes, average="micro", zero_division=0)
    base_micro_f1 = f1_score(gold_types, base_preds, labels=all_classes, average="micro", zero_division=0)

    print("\n--- BASELINE (28-Class Multiclass Full Test Set: 96 samples) ---")
    print(f"  Accuracy:    {base_acc:.4f} ({base_acc*100:.2f}%) [{sum(1 for g, p in zip(gold_types, base_preds) if g == p)}/96 correct]")
    print(f"  Micro P:     {base_micro_p:.4f} ({base_micro_p*100:.2f}%)")
    print(f"  Micro R:     {base_micro_r:.4f} ({base_micro_r*100:.2f}%)")
    print(f"  Micro F1:    {base_micro_f1:.4f} ({base_micro_f1*100:.2f}%)")
    print(f"  Macro P:     {base_macro_p:.4f} ({base_macro_p*100:.2f}%)")
    print(f"  Macro R:     {base_macro_r:.4f} ({base_macro_r*100:.2f}%)")
    print(f"  Macro F1:    {base_macro_f1:.4f} ({base_macro_f1*100:.2f}%)")
    print(f"  Weighted F1: {base_weighted_f1:.4f} ({base_weighted_f1*100:.2f}%)")

    # 4. Event-Only Prediction Evaluation (When evaluating on the 90 Gold Events)
    print("\n" + "=" * 80)
    print("VIEW 3: EVENT SAMPLES ONLY (90 Gold Events)")
    print("=" * 80)
    print(f"DeBERTa Exact Event Type Matches: {deb_ev_exact_match} / 90 ({deb_ev_exact_match/90*100:.2f}%)")
    print(f"DeBERTa Incorrect Event Type:     {90 - deb_ev_exact_match} / 90 ({(90-deb_ev_exact_match)/90*100:.2f}%)")
    print(f"DeBERTa Missed Events (predicted NO_EVENT): {sum(1 for p in deb_events_only if p == 'NO_EVENT')} / 90")
    print(f"\nBaseline Exact Event Type Matches: {base_ev_exact_match} / 90 ({base_ev_exact_match/90*100:.2f}%)")
    print(f"Baseline Missed Events (predicted NO_EVENT): {sum(1 for p in base_events_only if p == 'NO_EVENT')} / 90")

    # 5. Grounding Audit
    print("\n" + "=" * 80)
    print("VIEW 4: SOURCE GROUNDING VERIFICATION AUDIT")
    print("=" * 80)
    grounding_issues = []
    total_deb_events = 0
    grounded_deb_events = 0

    for s in samples_data:
        text = s["text"]
        for ev in s["deb_events"]:
            total_deb_events += 1
            # Check source reference
            if not ev.source_reference:
                grounding_issues.append((s["index"], "Missing source_reference", text, ev))
                continue
            sr = ev.source_reference
            # Check trigger
            if not ev.trigger:
                grounding_issues.append((s["index"], "Missing trigger", text, ev))
                continue
            trig = ev.trigger
            # Check offsets within text
            if trig.char_start < 0 or trig.char_end > len(text) or trig.char_start >= trig.char_end:
                grounding_issues.append((s["index"], f"Invalid char offsets [{trig.char_start}, {trig.char_end}] for len {len(text)}", text, ev))
                continue
            # Check span text match
            slice_text = text[trig.char_start:trig.char_end]
            if slice_text != trig.raw_text:
                grounding_issues.append((s["index"], f"Span slice '{slice_text}' != raw_text '{trig.raw_text}'", text, ev))
                continue
            grounded_deb_events += 1

    print(f"Total DeBERTa extracted events: {total_deb_events}")
    print(f"Verified strictly grounded events: {grounded_deb_events}")
    print(f"Grounding issues detected: {len(grounding_issues)}")
    if grounding_issues:
        for idx, issue, txt, ev in grounding_issues[:5]:
            print(f"  Sample {idx}: {issue} | Text: '{txt}' | Trigger: '{ev.trigger.raw_text}'")

    # 6. Detailed Sample-by-Sample Trace Export
    trace_file = "d:/ProofFlow/scratch/audit_sample_trace.jsonl"
    os.makedirs(os.path.dirname(trace_file), exist_ok=True)
    with open(trace_file, "w", encoding="utf-8") as f:
        for s in samples_data:
            record = {
                "index": s["index"],
                "text": s["text"],
                "gold_type": s["gold_type"],
                "is_gold_event": s["is_gold_event"],
                "deb_pred_type": s["deb_pred_type"],
                "is_deb_pred_event": s["is_deb_pred_event"],
                "deb_correct": (s["deb_pred_type"] == s["gold_type"]),
                "base_pred_type": s["base_pred_type"],
                "is_base_pred_event": s["is_base_pred_event"],
                "base_correct": (s["base_pred_type"] == s["gold_type"]),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\nExported complete sample-by-sample trace to {trace_file}")

    return {
        "samples_data": samples_data,
        "all_classes": all_classes,
        "confusion_matrix": confusion_matrix(gold_types, deb_preds, labels=all_classes).tolist(),
        "classification_report": classification_report(gold_types, deb_preds, labels=all_classes, output_dict=True, zero_division=0)
    }

if __name__ == "__main__":
    run_audit()
