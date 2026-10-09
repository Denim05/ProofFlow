import os
from ml.evaluation.model_comparison import run_model_comparison


def test_model_comparison_harness():
    report = run_model_comparison()
    assert report["test_sample_count"] > 0
    assert "deterministic_baseline" in report
    base_stats = report["deterministic_baseline"]
    # Baseline invariants: 100% source grounded and 0% unsupported
    assert base_stats["grounding_rate"] == 1.0
    assert base_stats["unsupported_rate"] == 0.0
    assert base_stats["precision"] >= 0.35
    assert base_stats["recall"] >= 0.05
    assert "disagreements_count" in report
    assert "baseline_per_class" in report
    assert "baseline_confusion_matrix" in report
    assert report["baseline_binary_detection"]["precision"] == 1.0
    if report["deberta_status"] == "EVALUATED":
        assert report["deberta_binary_detection"]["accuracy"] == 1.0
        assert report["finetuned_deberta_v3"]["grounding_rate"] == 1.0


def test_improved_dataset_leakage_and_integrity():
    import json
    from difflib import SequenceMatcher

    def load_texts(path):
        with open(path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    train_data = load_texts("ml/events/data/train.jsonl")
    val_data = load_texts("ml/events/data/val.jsonl")
    test_data = load_texts("ml/events/data/test.jsonl")

    assert len(train_data) >= 400
    assert len(val_data) >= 80
    assert len(test_data) >= 80

    train_texts = {s["text"].strip().lower() for s in train_data}
    val_texts = {s["text"].strip().lower() for s in val_data}
    test_texts = {s["text"].strip().lower() for s in test_data}

    # Invariant: Zero exact duplicates across splits
    assert len(train_texts & val_texts) == 0
    assert len(train_texts & test_texts) == 0
    assert len(val_texts & test_texts) == 0

    # Invariant: No near duplicates between train and test exceeding 0.88 similarity
    for t_text in list(test_texts)[:20]:
        for tr_text in list(train_texts)[:20]:
            sim = SequenceMatcher(None, t_text, tr_text).ratio()
            assert sim < 0.88, f"Near-duplicate leakage detected: '{t_text}' vs '{tr_text}'"


def test_improved_deberta_checkpoint_summary_invariants():
    import json

    summary_path = "ml/checkpoints/deberta_v3_event/training_summary.json"
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        assert summary["status"] == "COMPLETED"
        assert summary["model_name"] == "microsoft/deberta-v3-base"
        assert summary["dataset_version"] == "2.0.0-improved"
        assert summary["dataset_splits"]["train_count"] == 483
        assert summary["dataset_splits"]["val_count"] == 104
        assert summary["dataset_splits"]["test_count"] == 96
        assert len(summary["history"]) > 0


