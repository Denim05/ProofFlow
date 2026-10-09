import json
from collections import Counter
from sklearn.metrics import classification_report, confusion_matrix
import csv

def main():
    with open("scratch/audit_sample_trace.jsonl", "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    gold = [r["gold_type"] for r in records]
    deb_pred = [r["deb_pred_type"] for r in records]
    base_pred = [r["base_pred_type"] for r in records]

    classes = sorted(list(set(gold + deb_pred + base_pred)))

    print("="*80)
    print("DEBERTA-V3 CLASSIFICATION REPORT (SKLEARN):")
    print("="*80)
    deb_rep = classification_report(gold, deb_pred, labels=classes, zero_division=0)
    print(deb_rep)

    print("\n" + "="*80)
    print("BASELINE CLASSIFICATION REPORT (SKLEARN):")
    print("="*80)
    base_rep = classification_report(gold, base_pred, labels=classes, zero_division=0)
    print(base_rep)

    # Save per-class metrics to json
    deb_dict = classification_report(gold, deb_pred, labels=classes, output_dict=True, zero_division=0)
    base_dict = classification_report(gold, base_pred, labels=classes, output_dict=True, zero_division=0)

    with open("scratch/audit_metrics_summary.json", "w", encoding="utf-8") as f:
        json.dump({"deberta": deb_dict, "baseline": base_dict, "classes": classes}, f, indent=2)

    # Confusion matrix
    cm = confusion_matrix(gold, deb_pred, labels=classes)
    with open("scratch/deberta_confusion_matrix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Gold \\ Pred"] + classes)
        for c_name, row in zip(classes, cm):
            writer.writerow([c_name] + list(row))
    print("Saved confusion matrix to scratch/deberta_confusion_matrix.csv")

if __name__ == "__main__":
    main()
