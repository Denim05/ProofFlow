from decimal import Decimal
import json
import os
from typing import Any, Dict, List
from ml.events.pipeline import EventExtractionPipeline
from ml.schemas.entity import MonetaryValue
from ml.schemas.event import Event, EventModality, EventPolarity, EventTense
from ml.schemas.evidence_text import (
    EvidenceText,
    ExtractionQualityMetrics,
    ExtractionQualityState,
    PageExtractionMethod,
    PageLayout,
    TextBlock,
    TextLine,
    TextSpan,
)

BENCHMARK_FILE = os.path.join(os.path.dirname(__file__), "benchmarks", "event_benchmark.jsonl")


def create_mock_evidence_text(text: str, case_id: str) -> EvidenceText:
    """Helper to construct EvidenceText for evaluating event extraction."""
    span = TextSpan(
        span_index=0,
        raw_text=text,
        normalized_text=text,
        bounding_box=[50.0, 50.0, 550.0, 100.0],
        raw_char_start=0,
        raw_char_end=len(text),
        extraction_confidence=1.0,
    )
    line = TextLine(line_index=0, raw_text=text, spans=[span], line_confidence=1.0)
    block = TextBlock(block_index=0, block_type="paragraph", lines=[line], raw_text=text)
    page = PageLayout(
        page_number=1,
        width=595.0,
        height=842.0,
        extraction_method=PageExtractionMethod.NATIVE_PDF,
        quality_state=ExtractionQualityState.PASS,
        blocks=[block],
        raw_page_text=text,
        normalized_page_text=text,
    )
    return EvidenceText(
        text_id=f"txt_{case_id}",
        evidence_id=f"evi_{case_id}",
        case_id=case_id,
        full_raw_text=text,
        full_normalized_text=text,
        pages=[page],
        overall_quality_state=ExtractionQualityState.PASS,
        quality_metrics=ExtractionQualityMetrics(raw_character_count=len(text)),
        model_metadata={"pipeline_version": "v0.4.0-event-eval"},
    )


def run_event_evaluation() -> Dict[str, Any]:
    """Evaluates the event extraction foundation against the controlled synthetic benchmark."""
    pipeline = EventExtractionPipeline()

    if not os.path.exists(BENCHMARK_FILE):
        raise FileNotFoundError(f"Benchmark file not found: {BENCHMARK_FILE}")

    samples = []
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    total_gold_events = 0
    total_extracted_events = 0
    type_true_positives = 0

    negation_eval_count = 0
    negation_correct_count = 0

    modal_eval_count = 0
    modal_correct_count = 0

    argument_slots_evaluated = 0
    argument_slots_correct = 0

    grounded_events_count = 0
    unsupported_events_count = 0
    all_monetary_exact_decimal = True

    case_eval_details = []

    for sample in samples:
        cid = sample["case_id"]
        text = sample["text"]
        gold_events = sample["gold_events"]
        total_gold_events += len(gold_events)

        # Context anchor for relative time chat
        doc_anchor = None
        if "chat" in cid or "relative" in cid:
            doc_anchor = {"anchor_date": "2026-10-08T10:00:00Z", "source": "chat_header"}

        evidence_text = create_mock_evidence_text(text, cid)
        extracted_events = pipeline.process_evidence(evidence_text, document_anchor=doc_anchor)
        total_extracted_events += len(extracted_events)

        for ev in extracted_events:
            # 1. Check Source Provenance
            if ev.trigger and ev.trigger.source_reference and ev.source_reference.evidence_id:
                grounded_events_count += 1
            else:
                unsupported_events_count += 1

            # 2. Check Monetary Decimal
            if ev.amount:
                if not isinstance(ev.amount.value, Decimal):
                    all_monetary_exact_decimal = False

        # Match against gold events
        matched_gold_indices = set()
        for ev in extracted_events:
            for g_idx, gold in enumerate(gold_events):
                if g_idx in matched_gold_indices:
                    continue
                if ev.event_type.value == gold["event_type"]:
                    matched_gold_indices.add(g_idx)
                    type_true_positives += 1

                    # Evaluate Negation Polarity
                    negation_eval_count += 1
                    if ev.polarity.value == gold["polarity"]:
                        negation_correct_count += 1

                    # Evaluate Modality & Tense
                    modal_eval_count += 1
                    if ev.modality.value == gold["modality"] and ev.tense.value == gold["tense"]:
                        modal_correct_count += 1

                    # Evaluate Arguments
                    if gold.get("has_amount"):
                        argument_slots_evaluated += 1
                        if ev.amount is not None:
                            argument_slots_correct += 1

                    if gold.get("has_order"):
                        argument_slots_evaluated += 1
                        if ev.order_reference is not None:
                            argument_slots_correct += 1

                    if gold.get("has_txn"):
                        argument_slots_evaluated += 1
                        if ev.transaction_reference is not None:
                            argument_slots_correct += 1

                    if gold.get("has_temporal"):
                        argument_slots_evaluated += 1
                        if ev.temporal_information is not None:
                            argument_slots_correct += 1

                    if gold.get("missing_order"):
                        argument_slots_evaluated += 1
                        # Must remain None, never invented!
                        if ev.order_reference is None:
                            argument_slots_correct += 1

                    if gold.get("missing_amount"):
                        argument_slots_evaluated += 1
                        # Must remain None, never invented!
                        if ev.amount is None:
                            argument_slots_correct += 1
                    break

        case_eval_details.append({
            "case_id": cid,
            "gold_count": len(gold_events),
            "extracted_count": len(extracted_events),
            "matched_count": len(matched_gold_indices),
        })

    # Metric calculations
    p_type = round(type_true_positives / total_extracted_events, 4) if total_extracted_events > 0 else 0.0
    r_type = round(type_true_positives / total_gold_events, 4) if total_gold_events > 0 else 0.0
    f1_type = round(2 * p_type * r_type / (p_type + r_type), 4) if (p_type + r_type) > 0 else 0.0

    negation_acc = round(negation_correct_count / negation_eval_count, 4) if negation_eval_count > 0 else 0.0
    modal_acc = round(modal_correct_count / modal_eval_count, 4) if modal_eval_count > 0 else 0.0
    arg_acc = round(argument_slots_correct / argument_slots_evaluated, 4) if argument_slots_evaluated > 0 else 0.0
    grounding_rate = round(grounded_events_count / total_extracted_events, 4) if total_extracted_events > 0 else 0.0
    unsupported_rate = round(unsupported_events_count / total_extracted_events, 4) if total_extracted_events > 0 else 0.0

    eval_report = {
        "evaluation_name": "ProofFlow ML Track 4 Event Extraction Benchmark",
        "benchmark_type": "controlled synthetic benchmark (not representative of production/generalization accuracy)",
        "sample_count": len(samples),
        "event_metrics": {
            "total_gold_events": total_gold_events,
            "total_extracted_events": total_extracted_events,
            "type_true_positives": type_true_positives,
            "precision": p_type,
            "recall": r_type,
            "f1": f1_type,
        },
        "nuance_accuracy": {
            "negation_accuracy": negation_acc,
            "modality_and_tense_accuracy": modal_acc,
            "argument_binding_accuracy": arg_acc,
        },
        "grounding_invariants": {
            "grounding_rate": grounding_rate,
            "unsupported_event_rate": unsupported_rate,
            "monetary_exact_decimal_verified": all_monetary_exact_decimal,
        },
        "candidate_model_feasibility": {
            "deterministic_baseline": {
                "status": "EVALUATED",
                "environment": "Python 3.13 (Native, Windows)",
                "dependencies": "Zero external ML weights; linear-time deterministic regexes + EntityMentions",
            },
            "deberta_transformer": {
                "status": "NOT EVALUATED",
                "reason": "PyTorch / Transformers not installed in runtime virtualenv; requires ~500MB download; GPU unavailable.",
            },
            "roberta_transformer": {
                "status": "NOT EVALUATED",
                "reason": "PyTorch / Transformers not installed in runtime virtualenv; requires ~500MB download; GPU unavailable.",
            },
            "layoutlmv3_transformer": {
                "status": "NOT EVALUATED",
                "reason": "Requires PyTorch, Detectron2, and vision-backbone checkpoint weights (~500MB+); unsupported in lightweight offline test suite.",
            },
        },
        "case_eval_details": case_eval_details,
    }

    out_file = os.path.join(os.path.dirname(__file__), "event_eval_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)

    return eval_report


def test_event_benchmark_evaluation():
    """Unit test executing the event evaluation benchmark."""
    report = run_event_evaluation()
    assert report["event_metrics"]["total_gold_events"] > 0
    assert report["event_metrics"]["precision"] >= 0.85
    assert report["event_metrics"]["recall"] >= 0.85
    assert report["event_metrics"]["f1"] >= 0.85
    assert report["nuance_accuracy"]["negation_accuracy"] >= 0.90
    assert report["nuance_accuracy"]["modality_and_tense_accuracy"] >= 0.85
    assert report["grounding_invariants"]["grounding_rate"] == 1.0
    assert report["grounding_invariants"]["unsupported_event_rate"] == 0.0
    assert report["grounding_invariants"]["monetary_exact_decimal_verified"] is True


if __name__ == "__main__":
    rep = run_event_evaluation()
    print("=== ProofFlow ML Track 4 Event Evaluation ===")
    print(f"Benchmark: {rep['benchmark_type']}")
    print(f"Events F1: {rep['event_metrics']['f1']} (P: {rep['event_metrics']['precision']}, R: {rep['event_metrics']['recall']})")
    print(f"Negation Acc: {rep['nuance_accuracy']['negation_accuracy']}")
    print(f"Modality Acc: {rep['nuance_accuracy']['modality_and_tense_accuracy']}")
    print(f"Argument Acc: {rep['nuance_accuracy']['argument_binding_accuracy']}")
    print(f"Grounding Rate: {rep['grounding_invariants']['grounding_rate']}")
