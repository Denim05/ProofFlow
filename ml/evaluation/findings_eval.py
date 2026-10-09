import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import re
from typing import Any, Dict, List, Optional
from bson import Decimal128

from app.services.finding_service import FindingService
from tests.conftest import FakeAsyncDatabase

BENCHMARK_PATH = os.path.join(
    os.path.dirname(__file__), "..", "datasets", "synthetic_benchmark", "findings_scenarios_v1.json"
)
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "findings_eval_results.json")

FORBIDDEN_FRAUD_WORDS = re.compile(
    r"\b(fraud|fraudulent|scam|forgery|fake|deceit|criminal|authentic|falsity)\b",
    re.IGNORECASE,
)


def load_scenarios() -> Dict[str, Any]:
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def run_scenario(scenario: Dict[str, Any]) -> Dict[str, Any]:
    sid = scenario["scenario_id"]
    fake_db = FakeAsyncDatabase()
    case_id = f"case_{sid}"
    user_id = "eval_user"

    # 1. Seed Case
    await fake_db.cases.insert_one({
        "case_id": case_id,
        "user_id": user_id,
        "title": scenario["description"][:100],
        "status": "READY",
        "created_at": datetime.now(timezone.utc),
    })

    # 2. Seed Evidence Documents
    for evi in scenario["evidence_documents"]:
        await fake_db.evidence.insert_one({
            "evidence_id": evi["evidence_id"],
            "case_id": case_id,
            "user_id": user_id,
            "original_filename": evi["filename"],
            "active_processing_version": evi.get("active_processing_version", 1),
            "processing_version": evi.get("active_processing_version", 1),
            "status": evi.get("status", "READY"),
            "created_at": datetime.now(timezone.utc),
        })

    # 3. Seed Events
    for ev in scenario["events"]:
        amt = ev.get("amount_value")
        # Support Decimal / Decimal128 encoding
        amt_val = Decimal128(str(amt)) if amt is not None else None

        await fake_db.events.insert_one({
            "event_id": ev["event_id"],
            "case_id": case_id,
            "evidence_id": ev["evidence_id"],
            "user_id": user_id,
            "processing_version": ev.get("processing_version", 1),
            "is_active": ev.get("is_active", True),
            "event_type": ev["event_type"],
            "decision_state": ev.get("decision_state", "VALIDATED"),
            "review_reasons": ev.get("review_reasons", []),
            "trigger_raw_text": ev["trigger_raw_text"],
            "char_start": ev.get("char_start", 0),
            "char_end": ev.get("char_end", 0),
            "page_number": ev.get("page_number", 1),
            "order_reference": ev.get("order_reference"),
            "transaction_reference": ev.get("transaction_reference"),
            "temporal_information": ev.get("temporal_information"),
            "amount_currency": ev.get("amount_currency"),
            "amount_value": amt_val,
            "polarity": ev.get("polarity", "POSITIVE"),
            "modality": ev.get("modality", "ASSERTED"),
            "tense": ev.get("tense", "PAST"),
            "model_confidence": ev.get("model_confidence", 1.0),
            "created_at": datetime.now(timezone.utc),
        })

    # 4. Execute FindingService
    findings_resp = await FindingService.compute_case_findings(
        case_id=case_id,
        user_id=user_id,
        db=fake_db,
    )

    actual_findings = findings_resp.items
    actual_count = len(actual_findings)
    expected = scenario["expected"]
    expected_count = expected["findings_count"]

    # 5. Evaluate checks
    passed = True
    failure_reasons = []

    if actual_count != expected_count:
        passed = False
        failure_reasons.append(f"Count mismatch: expected {expected_count}, got {actual_count}")

    if expected_count > 0 and actual_count > 0:
        f = actual_findings[0]

        if "conflict_state" in expected and f.conflict_state != expected["conflict_state"]:
            passed = False
            failure_reasons.append(f"ConflictState mismatch: expected {expected['conflict_state']}, got {f.conflict_state}")

        if "severity" in expected and f.severity != expected["severity"]:
            passed = False
            failure_reasons.append(f"Severity mismatch: expected {expected['severity']}, got {f.severity}")

        if "finding_type" in expected and f.finding_type != expected["finding_type"]:
            passed = False
            failure_reasons.append(f"FindingType mismatch: expected {expected['finding_type']}, got {f.finding_type}")

        if "expected_title_contains" in expected and expected["expected_title_contains"] not in f.title:
            passed = False
            failure_reasons.append(f"Title missing '{expected['expected_title_contains']}': got '{f.title}'")

        if "citations_min" in expected and len(f.citations) < expected["citations_min"]:
            passed = False
            failure_reasons.append(f"Citations count < {expected['citations_min']}: got {len(f.citations)}")

    # 6. Global Safety Check: Forbidden Fraud / Deceit Language
    for f in actual_findings:
        text_corpus = f"{f.title} {f.summary}"
        matched = FORBIDDEN_FRAUD_WORDS.findall(text_corpus)
        if matched:
            passed = False
            failure_reasons.append(f"Violated conservative language policy: found forbidden terms {matched}")

        # Citation Integrity Check
        for cit in f.citations:
            if not cit.evidence_id:
                passed = False
                failure_reasons.append("Citation missing evidence_id")
            if not cit.original_filename:
                passed = False
                failure_reasons.append("Citation missing original_filename")
            if cit.char_start == 0 and cit.char_end == 0:
                passed = False
                failure_reasons.append("Citation exposed raw default 0..0 character offset instead of None")

    return {
        "scenario_id": sid,
        "category": scenario["category"],
        "passed": passed,
        "expected_count": expected_count,
        "actual_count": actual_count,
        "failure_reasons": failure_reasons,
        "findings_titles": [f.title for f in actual_findings],
    }


async def evaluate_findings_suite() -> Dict[str, Any]:
    benchmark_data = load_scenarios()
    scenarios = benchmark_data["scenarios"]

    scenario_results = []
    scen_tp, scen_fp, scen_fn, scen_tn = 0, 0, 0, 0
    find_tp, find_fp, find_fn = 0, 0, 0

    for scen in scenarios:
        res = await run_scenario(scen)
        scenario_results.append(res)

        exp_count = scen["expected"]["findings_count"]
        act_count = res["actual_count"]

        # 1. Scenario-level evaluation (Binary: issue expected vs issue detected)
        exp_has_issue = exp_count > 0
        act_has_issue = act_count > 0

        if exp_has_issue and act_has_issue and res["passed"]:
            scen_tp += 1
        elif not exp_has_issue and not act_has_issue and res["passed"]:
            scen_tn += 1
        elif not exp_has_issue and act_has_issue:
            scen_fp += 1
        elif exp_has_issue and not act_has_issue:
            scen_fn += 1
        else:
            # Policy failure or count mismatch on positive scenario
            scen_fn += 1

        # 2. Finding-level micro evaluation
        if res["passed"]:
            find_tp += exp_count
            # If actual exceeded expected (even if passed somehow)
            if act_count > exp_count:
                find_fp += (act_count - exp_count)
        else:
            if exp_count == 0:
                find_fp += act_count
            else:
                if act_count == 0:
                    find_fn += exp_count
                elif act_count < exp_count:
                    find_tp += act_count
                    find_fn += (exp_count - act_count)
                else:
                    find_tp += exp_count
                    find_fp += (act_count - exp_count)

    total_scenarios = len(scenarios)
    passed_scenarios = sum(1 for r in scenario_results if r["passed"])

    scen_prec = (scen_tp / (scen_tp + scen_fp)) if (scen_tp + scen_fp) > 0 else 1.0
    scen_rec = (scen_tp / (scen_tp + scen_fn)) if (scen_tp + scen_fn) > 0 else 1.0
    scen_f1 = (2 * scen_prec * scen_rec / (scen_prec + scen_rec)) if (scen_prec + scen_rec) > 0 else 0.0
    scen_fpr = (scen_fp / (scen_fp + scen_tn)) if (scen_fp + scen_tn) > 0 else 0.0

    find_prec = (find_tp / (find_tp + find_fp)) if (find_tp + find_fp) > 0 else 1.0
    find_rec = (find_tp / (find_tp + find_fn)) if (find_tp + find_fn) > 0 else 1.0
    find_f1 = (2 * find_prec * find_rec / (find_prec + find_rec)) if (find_prec + find_rec) > 0 else 0.0

    report = {
        "benchmark_version": benchmark_data["benchmark_version"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total_scenarios,
        "passed_scenarios": passed_scenarios,
        "scenario_pass_rate": round(passed_scenarios / total_scenarios, 4),
        "scenario_level_metrics": {
            "unit": "scenario_outcome",
            "true_positives": scen_tp,
            "true_negatives": scen_tn,
            "false_positives": scen_fp,
            "false_negatives": scen_fn,
            "precision": round(scen_prec, 4),
            "recall": round(scen_rec, 4),
            "f1_score": round(scen_f1, 4),
            "false_positive_rate": round(scen_fpr, 4),
            "denominators": {
                "precision": f"{scen_tp} / ({scen_tp} + {scen_fp})",
                "recall": f"{scen_tp} / ({scen_tp} + {scen_fn})",
                "fpr": f"{scen_fp} / ({scen_fp} + {scen_tn})",
            },
        },
        "finding_level_metrics": {
            "unit": "individual_finding",
            "true_positives": find_tp,
            "false_positives": find_fp,
            "false_negatives": find_fn,
            "precision": round(find_prec, 4),
            "recall": round(find_rec, 4),
            "f1_score": round(find_f1, 4),
            "denominators": {
                "precision": f"{find_tp} / ({find_tp} + {find_fp})",
                "recall": f"{find_tp} / ({find_tp} + {find_fn})",
            },
        },
        "scenario_details": scenario_results,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def main():
    print("Running ProofFlow Findings Quality Evaluation Suite...")
    report = asyncio.run(evaluate_findings_suite())
    print(f"Total Scenarios: {report['total_scenarios']}")
    print(f"Passed Scenarios: {report['passed_scenarios']} / {report['total_scenarios']} ({report['scenario_pass_rate']*100:.1f}%)")
    scen_m = report["scenario_level_metrics"]
    print(f"Scenario-Level: Precision={scen_m['precision']*100:.1f}% ({scen_m['denominators']['precision']}), "
          f"Recall={scen_m['recall']*100:.1f}% ({scen_m['denominators']['recall']}), "
          f"F1={scen_m['f1_score']*100:.1f}%, FPR={scen_m['false_positive_rate']*100:.1f}% ({scen_m['denominators']['fpr']})")
    find_m = report["finding_level_metrics"]
    print(f"Finding-Level:  Precision={find_m['precision']*100:.1f}% ({find_m['denominators']['precision']}), "
          f"Recall={find_m['recall']*100:.1f}% ({find_m['denominators']['recall']}), "
          f"F1={find_m['f1_score']*100:.1f}%")
    for s in report["scenario_details"]:
        status_str = "PASS" if s["passed"] else f"FAIL ({', '.join(s['failure_reasons'])})"
        print(f"  [{s['category']}] {s['scenario_id']}: {status_str}")


if __name__ == "__main__":
    main()
