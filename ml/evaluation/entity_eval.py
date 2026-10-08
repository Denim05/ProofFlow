from decimal import Decimal
import json
import os
from typing import Any, Dict, List
from ml.entities.pipeline import EntityExtractionPipeline
from ml.schemas.entity import MonetaryValue, PhoneNumberValue
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

BENCHMARK_FILE = os.path.join(os.path.dirname(__file__), "benchmarks", "entity_benchmark.jsonl")


def create_mock_evidence_text(text: str, doc_id: str) -> EvidenceText:
    """Constructs a minimal synthetic EvidenceText container for evaluating text extraction."""
    # Build single span, line, block, page
    span = TextSpan(
        span_index=0,
        raw_text=text,
        normalized_text=text,
        bounding_box=[50.0, 50.0, 500.0, 100.0],
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
        text_id=f"txt_{doc_id}",
        evidence_id=f"evi_{doc_id}",
        case_id="case_eval",
        full_raw_text=text,
        full_normalized_text=text,
        pages=[page],
        overall_quality_state=ExtractionQualityState.PASS,
        quality_metrics=ExtractionQualityMetrics(raw_character_count=len(text)),
        model_metadata={"pipeline_version": "v0.3.0-eval"},
    )


def run_entity_evaluation() -> Dict[str, Any]:
    """Runs entity extraction evaluation over the curated benchmark dataset."""
    pipeline = EntityExtractionPipeline()

    if not os.path.exists(BENCHMARK_FILE):
        raise FileNotFoundError(f"Benchmark file not found at: {BENCHMARK_FILE}")

    samples = []
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    total_gold = 0
    total_extracted = 0
    true_positives = 0
    document_results = []

    case_h_evaluated = False
    case_h_ambiguity_preserved = False
    ambiguous_date_preserved = False
    unanchored_phone_safe = False
    monetary_decimal_verified = True

    for sample in samples:
        doc_id = sample["document_id"]
        text = sample["text"]
        gold_entities = sample["gold_entities"]
        total_gold += len(gold_entities)

        # Context anchor for chat logs
        doc_anchor = None
        if "chat" in doc_id:
            doc_anchor = {"anchor_date": "2026-10-08T10:00:00Z", "source": "chat_header"}

        evidence_text = create_mock_evidence_text(text, doc_id)
        mentions = pipeline.process_evidence_text(evidence_text, document_anchor=doc_anchor)
        total_extracted += len(mentions)

        doc_tp = 0
        for gold in gold_entities:
            g_type = gold["type"]
            g_raw = gold["raw"].strip()

            # Check for matching extracted mention
            match = any(
                m.entity_type == g_type and (g_raw in m.raw_value or m.raw_value in g_raw)
                for m in mentions
            )
            if match:
                doc_tp += 1
                true_positives += 1

        # Specific safety checks
        for m in mentions:
            # 1. Decimal verification for monetary values
            if isinstance(m.normalized_value, MonetaryValue):
                if not isinstance(m.normalized_value.value, Decimal):
                    monetary_decimal_verified = False

            # 2. Case H check
            if doc_id == "eval_doc_05_case_h_noisy_ocr" and "TXN-O09I82" in m.raw_value:
                case_h_evaluated = True
                if m.model_metadata.get("span_metadata", {}).get("is_ambiguous", False):
                    case_h_ambiguity_preserved = True

            # 3. Ambiguous date check (04/05/2026)
            if "04/05/2026" in m.raw_value and isinstance(m.normalized_value, dict):
                if m.normalized_value.get("ambiguous") is True:
                    ambiguous_date_preserved = True

            # 4. Unanchored phone check (9876543210)
            if isinstance(m.normalized_value, PhoneNumberValue):
                if m.normalized_value.country_code == "UNKNOWN" and m.normalized_value.e164_formatted is None:
                    unanchored_phone_safe = True

        document_results.append({
            "document_id": doc_id,
            "gold_count": len(gold_entities),
            "extracted_count": len(mentions),
            "true_positives": doc_tp,
        })

    precision = round(true_positives / total_extracted, 4) if total_extracted > 0 else 0.0
    recall = round(true_positives / total_gold, 4) if total_gold > 0 else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    eval_report = {
        "evaluation_name": "ProofFlow ML Track 3 Entity Extraction Benchmark",
        "sample_count": len(samples),
        "total_gold_entities": total_gold,
        "total_extracted_entities": total_extracted,
        "true_positives": true_positives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "safety_checks": {
            "monetary_uses_exact_decimal": monetary_decimal_verified,
            "case_h_evaluated": case_h_evaluated,
            "case_h_ambiguity_preserved": case_h_ambiguity_preserved,
            "ambiguous_date_preserved": ambiguous_date_preserved,
            "unanchored_phone_preserves_unknown_country": unanchored_phone_safe,
        },
        "document_results": document_results,
    }

    out_file = os.path.join(os.path.dirname(__file__), "entity_eval_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)

    return eval_report


def test_entity_benchmark_evaluation():
    """Unit test runner for the entity benchmark evaluation."""
    report = run_entity_evaluation()
    assert report["total_gold_entities"] > 0
    assert report["precision"] >= 0.85
    assert report["recall"] >= 0.85
    assert report["f1"] >= 0.85
    assert report["safety_checks"]["monetary_uses_exact_decimal"] is True
    assert report["safety_checks"]["case_h_ambiguity_preserved"] is True
    assert report["safety_checks"]["ambiguous_date_preserved"] is True
    assert report["safety_checks"]["unanchored_phone_preserves_unknown_country"] is True


if __name__ == "__main__":
    rep = run_entity_evaluation()
    print("=== ML Track 3 Entity Evaluation Results ===")
    print(f"Samples: {rep['sample_count']}")
    print(f"Precision: {rep['precision']}, Recall: {rep['recall']}, F1: {rep['f1']}")
    print(f"Safety Checks: {rep['safety_checks']}")
