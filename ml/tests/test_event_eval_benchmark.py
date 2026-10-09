from ml.evaluation.event_eval import run_event_evaluation


def test_event_benchmark_execution():
    report = run_event_evaluation()
    assert report["event_metrics"]["total_gold_events"] == 11
    assert report["event_metrics"]["precision"] >= 0.85
    assert report["event_metrics"]["recall"] >= 0.85
    assert report["event_metrics"]["f1"] >= 0.85
    assert report["nuance_accuracy"]["negation_accuracy"] >= 0.90
    assert report["nuance_accuracy"]["modality_and_tense_accuracy"] >= 0.85
    assert report["grounding_invariants"]["grounding_rate"] == 1.0
    assert report["grounding_invariants"]["unsupported_event_rate"] == 0.0
    assert report["grounding_invariants"]["monetary_exact_decimal_verified"] is True
