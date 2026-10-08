import json
import os
import pytest
from ml.schemas.source_reference import SourceReference
from ml.schemas.model_metadata import ModelMetadata
from ml.schemas.entity import Entity, EntityType, MonetaryValue
from ml.schemas.event import Event, EventType
from ml.schemas.claim import Claim, Modality, EpistemicStatus
from ml.schemas.relationship import Relationship, RelationshipType
from ml.schemas.finding import Finding, FindingType, InconsistencyTier, ConflictState, CoverageState

BENCHMARK_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "datasets", "synthetic_benchmark")
)


def test_source_reference_validation():
    ref = SourceReference(evidence_id="evi_100", page_number=1, source_type="PDF")
    assert ref.evidence_id == "evi_100"
    assert ref.page_number == 1


def test_finding_requires_evidence_reference():
    meta = ModelMetadata(model_name="test", model_version="1.0", extraction_confidence=0.9)
    # Finding without evidence reference should raise validation error
    with pytest.raises(Exception):
        Finding(
            finding_id="fnd_1",
            case_id="case_1",
            finding_type=FindingType.POTENTIAL_INCONSISTENCY,
            title="Test Finding",
            summary="Test Summary",
            evidence_references=[],  # min_length=1 required
            model_metadata=meta,
        )


def test_validate_synthetic_benchmark_jsonl_files():
    """Verify all ground truth JSONL files in synthetic benchmark parse properly."""
    files = ["entities.jsonl", "events.jsonl", "claims.jsonl", "inconsistencies.jsonl"]
    for fname in files:
        fpath = os.path.join(BENCHMARK_DIR, fname)
        assert os.path.exists(fpath), f"File {fname} must exist"
        with open(fpath, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            assert len(lines) > 0
            for line in lines:
                data = json.loads(line)
                assert "annotation_id" in data
                assert "case_id" in data
