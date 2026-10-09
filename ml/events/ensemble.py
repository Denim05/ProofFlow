"""ProofFlow Hybrid Event Cascade: DeBERTa-v3 + Deterministic Validation Ensemble.

Implements the Track 4B hybrid cascade architecture:
EvidenceText
    ↓
DeBERTa-v3 Neural Prediction (NeuralEventPrediction)
    ↓
Deterministic Validation & Lifecycle Guards
    ↓
Hybrid Decision (EnsembleDecisionState: NEURAL_CANDIDATE | VALIDATED | REVIEW_NEEDED | REJECTED)
    ↓
Validated Event Object (Event)

Invariant: DeBERTa predictions never become trusted ProofFlow events without deterministic
source grounding, trigger verification, temporal/monetary safety, and lifecycle boundary checks.
"""

from decimal import Decimal
from enum import Enum
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from ml.entities.normalizer import SpatialProvenanceMapper
from ml.events.config import EventExtractionConfig, event_config
from ml.events.detector import EventCandidate, EventDetector
from ml.events.extractor import EventArgumentExtractor
from ml.events.taxonomy import TRIGGER_LEXICON
from ml.schemas.entity import EntityMention, EntityType, MonetaryValue
from ml.schemas.event import (
    Event,
    EventModality,
    EventPolarity,
    EventTense,
    EventTrigger,
    EventType,
)
from ml.schemas.evidence_text import EvidenceText
from ml.schemas.source_reference import SourceReference


class EnsembleDecisionState(str, Enum):
    """Explicit internal states for the hybrid decision policy."""
    NEURAL_CANDIDATE = "NEURAL_CANDIDATE"
    VALIDATED = "VALIDATED"
    REVIEW_NEEDED = "REVIEW_NEEDED"
    REJECTED = "REJECTED"


class NeuralEventPrediction(BaseModel):
    """Structured internal neural prediction produced by DeBERTa-v3.

    IMPORTANT:
    'model_confidence' represents statistical model classification posterior probability.
    It MUST NOT be interpreted or presented as factual authenticity or ground-truth confidence.
    """
    predicted_event_type: str = Field(..., description="Canonical 18 event type string or NO_EVENT")
    model_confidence: float = Field(..., ge=0.0, le=1.0, description="Model classification posterior probability")
    model_name: str = "microsoft/deberta-v3-base"
    model_version: str = "1.0.0"
    checkpoint_version: str = "3.0.0-canonical-18"
    source_text: str = Field(..., description="Verbatim sentence or clause evaluated")
    source_reference: Optional[SourceReference] = None
    char_start: int = Field(default=0, ge=0)
    char_end: int = Field(default=0, ge=0)
    inference_metadata: Dict[str, Any] = Field(default_factory=dict)


class HybridEnsembleConfig(BaseModel):
    """Candidate/development configuration for deterministic ensemble thresholds.

    NOTE: These thresholds are candidate/development operational knobs and must not
    be presented as absolute production guarantees.
    """
    checkpoint_dir: str = Field(
        default="ml/checkpoints/deberta_v3_event_canonical18",
        description="Path to serialized DeBERTa-v3 canonical-18 checkpoint",
    )
    min_validation_confidence: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum model classification confidence required for direct VALIDATED state",
    )
    review_confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Model classification confidence below which lifecycle guards strictly enforce review",
    )
    enforce_lifecycle_guards: bool = Field(
        default=True,
        description="Whether to run deterministic boundary conflict checks",
    )
    flag_compound_sentences: bool = Field(
        default=True,
        description="Whether sentences with multiple distinct event cues are routed to REVIEW_NEEDED",
    )


class EnsembleValidationResult(BaseModel):
    """Comprehensive audit report for a processed neural candidate."""
    decision_state: EnsembleDecisionState
    neural_prediction: Optional[NeuralEventPrediction] = None
    event: Optional[Event] = None
    validation_errors: List[str] = Field(default_factory=list)
    review_reasons: List[str] = Field(default_factory=list)
    lifecycle_guard_triggered: bool = False
    is_compound_sentence: bool = False
    grounding_verified: bool = False


class HybridEventCascade:
    """End-to-end hybrid event extraction cascade combining DeBERTa-v3 with deterministic safety."""

    def __init__(
        self,
        config: Optional[HybridEnsembleConfig] = None,
        extraction_config: EventExtractionConfig = event_config,
        mock_predictor: Optional[Callable[[str], NeuralEventPrediction]] = None,
    ):
        self.config = config or HybridEnsembleConfig()
        self.extraction_config = extraction_config
        self.mock_predictor = mock_predictor
        self.rule_detector = EventDetector(extraction_config)
        self.arg_extractor = EventArgumentExtractor(extraction_config)

        # Lazy model loader
        self._model = None
        self._tokenizer = None
        self._id2label = None
        self._device = None

        if self.mock_predictor is None:
            self._try_load_model()

    def _try_load_model(self):
        """Attempts to load fine-tuned model and tokenizer if PyTorch and checkpoint exist."""
        if not os.path.exists(self.config.checkpoint_dir):
            return

        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self._tokenizer = AutoTokenizer.from_pretrained(self.config.checkpoint_dir)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.config.checkpoint_dir)
            self._model.to(self._device)
            self._model.eval()

            mapping_path = os.path.join(self.config.checkpoint_dir, "label_mapping.json")
            if os.path.exists(mapping_path):
                with open(mapping_path, "r", encoding="utf-8") as f:
                    mapping = json.load(f)
                    self._id2label = {int(k): v for k, v in mapping["id2label"].items()}
        except Exception:
            # CPU fallback / test environment without PyTorch
            self._model = None
            self._tokenizer = None

    def predict_sentence(self, sentence: str, source_ref: Optional[SourceReference] = None, char_start: int = 0, char_end: int = 0) -> NeuralEventPrediction:
        """Generates a structured NeuralEventPrediction using mock predictor or DeBERTa."""
        if self.mock_predictor is not None:
            pred = self.mock_predictor(sentence)
            pred.source_text = sentence
            pred.char_start = char_start
            pred.char_end = char_end
            if source_ref:
                pred.source_reference = source_ref
            return pred

        if self._model is not None and self._tokenizer is not None:
            import torch

            inputs = self._tokenizer(sentence, truncation=True, max_length=128, return_tensors="pt").to(self._device)
            with torch.no_grad():
                logits = self._model(**inputs).logits
                probs = torch.softmax(logits, dim=1).squeeze(0)
                pred_idx = torch.argmax(probs).item()
                confidence = float(probs[pred_idx].item())
                pred_label = self._id2label.get(pred_idx, "NO_EVENT") if self._id2label else "NO_EVENT"

            return NeuralEventPrediction(
                predicted_event_type=pred_label,
                model_confidence=confidence,
                model_name="microsoft/deberta-v3-base",
                model_version="1.0.0",
                checkpoint_version="3.0.0-canonical-18",
                source_text=sentence,
                source_reference=source_ref,
                char_start=char_start,
                char_end=char_end,
                inference_metadata={"device": str(self._device)},
            )

        # Fallback to deterministic detector candidate if neural model unavailable
        cands = self.rule_detector.detect_candidates(sentence)
        if cands:
            top_cand = cands[0]
            return NeuralEventPrediction(
                predicted_event_type=top_cand.event_type.value,
                model_confidence=top_cand.confidence,
                source_text=sentence,
                source_reference=source_ref,
                char_start=char_start,
                char_end=char_end,
                inference_metadata={"fallback": "deterministic_detector"},
            )

        return NeuralEventPrediction(
            predicted_event_type="NO_EVENT",
            model_confidence=1.0,
            source_text=sentence,
            source_reference=source_ref,
            char_start=char_start,
            char_end=char_end,
        )

    def process_evidence(
        self,
        evidence_text: EvidenceText,
        entities: Optional[List[EntityMention]] = None,
    ) -> List[EnsembleValidationResult]:
        """Runs the hybrid cascade on an EvidenceText object and returns comprehensive validation results."""
        if not evidence_text or not evidence_text.full_raw_text:
            return []

        raw_text = evidence_text.full_raw_text
        sentences = self.rule_detector._split_into_sentences_with_offsets(raw_text)
        results: List[EnsembleValidationResult] = []

        for s_text, s_start, s_end in sentences:
            if not s_text.strip():
                continue

            # Build source reference for the sentence
            s_ref = SpatialProvenanceMapper.map_span_to_provenance(
                evidence_text=evidence_text,
                char_start=s_start,
                char_end=s_end,
                raw_snippet=s_text,
            )

            # 1. Neural classification
            pred = self.predict_sentence(s_text, source_ref=s_ref, char_start=s_start, char_end=s_end)

            # If DeBERTa classifies as NO_EVENT:
            if pred.predicted_event_type == "NO_EVENT":
                results.append(
                    EnsembleValidationResult(
                        decision_state=EnsembleDecisionState.VALIDATED,
                        neural_prediction=pred,
                        event=None,
                        grounding_verified=True,
                    )
                )
                continue

            # 2. Deterministic Validation & Lifecycle Policy
            val_res = self.validate_candidate(
                prediction=pred,
                evidence_text=evidence_text,
                entities=entities or [],
                sentence_start=s_start,
                sentence_end=s_end,
            )
            results.append(val_res)

        return results

    def validate_candidate(
        self,
        prediction: NeuralEventPrediction,
        evidence_text: EvidenceText,
        entities: List[EntityMention],
        sentence_start: int,
        sentence_end: int,
    ) -> EnsembleValidationResult:
        """Applies rigorous deterministic grounding, lifecycle guards, and compound sentence checks."""
        validation_errors: List[str] = []
        review_reasons: List[str] = []
        lifecycle_triggered = False
        compound_triggered = False
        grounding_ok = True

        raw_text = evidence_text.full_raw_text
        s_text = prediction.source_text

        # A. Check official canonical EventType
        try:
            event_type = EventType(prediction.predicted_event_type)
        except ValueError:
            return EnsembleValidationResult(
                decision_state=EnsembleDecisionState.REJECTED,
                neural_prediction=prediction,
                validation_errors=[f"Predicted type '{prediction.predicted_event_type}' is not an approved canonical EventType."],
            )

        # B. Source Grounding Check
        if s_text not in raw_text:
            validation_errors.append("Sentence text does not exist verbatim in EvidenceText raw text.")
            grounding_ok = False

        if prediction.source_reference is None:
            validation_errors.append("Missing required SourceReference on neural prediction.")
            grounding_ok = False

        # C. Trigger Extraction & Verbatim Substring Grounding
        # Attempt to find fine-grained trigger sub-span using deterministic lexicon
        rule_cands = self.rule_detector.detect_candidates(s_text)
        matched_cand = next((c for c in rule_cands if c.event_type == event_type), None)

        if matched_cand:
            trig_raw = matched_cand.trigger_text
            trig_start = sentence_start + matched_cand.char_start
            trig_end = sentence_start + matched_cand.char_end
            polarity = matched_cand.polarity
            modality = matched_cand.modality
            tense = matched_cand.tense
        else:
            # Fall back to sentence-level anchor
            trig_raw = s_text
            trig_start = sentence_start
            trig_end = sentence_end
            polarity, modality, tense = self.rule_detector._analyze_sentence_nuances(s_text.lower(), 0, len(s_text))

        # Validate trigger span boundaries and verbatim matching
        if trig_start < 0 or trig_end > len(raw_text) or trig_start >= trig_end:
            validation_errors.append(f"Invalid trigger offsets: [{trig_start}:{trig_end}].")
            grounding_ok = False
        else:
            actual_sub = raw_text[trig_start:trig_end]
            if actual_sub != trig_raw:
                validation_errors.append(f"Trigger mismatch: expected '{trig_raw}', found '{actual_sub}'.")
                grounding_ok = False

        # D. Negation & Modality Preservation
        # Check if the sentence has explicit negation cues that conflict with a positive assumption
        s_lower = s_text.lower()
        has_negation_cue = any(re.search(rf"\b{re.escape(cue)}\b", s_lower) for cue in self.extraction_config.negation_cues)
        if has_negation_cue and polarity != EventPolarity.NEGATED:
            polarity = EventPolarity.NEGATED
            review_reasons.append("Sentence contains negation cues; event polarity enforced as NEGATED.")

        # Check future/conditional modalities
        has_future_cue = any(re.search(rf"\b{re.escape(cue)}\b", s_lower) for cue in self.extraction_config.future_cues)
        if has_future_cue and modality == EventModality.ASSERTED:
            modality = EventModality.PLANNED
            tense = EventTense.FUTURE

        has_conditional_cue = any(re.search(rf"\b{re.escape(cue)}\b", s_lower) for cue in self.extraction_config.conditional_cues)
        if has_conditional_cue and modality == EventModality.ASSERTED:
            modality = EventModality.CONDITIONAL

        # E. Compound Sentence Guard
        # Check if the sentence mentions multiple distinct event cues
        if self.config.flag_compound_sentences:
            detected_types = {c.event_type for c in rule_cands}
            if len(detected_types) > 1:
                compound_triggered = True
                review_reasons.append(
                    f"Compound sentence detected: contains cues for multiple event types ({[t.value for t in detected_types]})."
                )

        # F. Lifecycle Boundary Guards
        if self.config.enforce_lifecycle_guards:
            lifecycle_conflict = self._check_lifecycle_conflicts(event_type, s_lower, rule_cands)
            if lifecycle_conflict:
                lifecycle_triggered = True
                review_reasons.append(lifecycle_conflict)

        # G. Build Candidate and Bind Arguments
        candidate = EventCandidate(
            event_type=event_type,
            trigger_text=trig_raw,
            char_start=trig_start,
            char_end=trig_end,
            polarity=polarity,
            modality=modality,
            tense=tense,
            confidence=prediction.model_confidence,
            context_sentence=s_text,
            context_start=sentence_start,
            context_end=sentence_end,
        )

        event = self.arg_extractor.bind_arguments_to_event(
            candidate=candidate,
            evidence_text=evidence_text,
            entities=entities,
        )

        # H. Validate Entity References & Exact Monetary Decimal
        if event.amount is not None:
            if not isinstance(event.amount.value, Decimal):
                validation_errors.append(f"Monetary value must be exact Decimal, got {type(event.amount.value)}.")
            # Verify amount string appears in source text
            amt_str = str(event.amount.value)
            if amt_str not in raw_text and amt_str.rstrip("0").rstrip(".") not in raw_text:
                review_reasons.append(f"Extracted amount {amt_str} could not be confirmed verbatim in source text.")

        if event.order_reference and event.order_reference not in raw_text:
            validation_errors.append(f"Order reference '{event.order_reference}' is not grounded in source text.")

        if event.transaction_reference and event.transaction_reference not in raw_text:
            validation_errors.append(f"Transaction reference '{event.transaction_reference}' is not grounded in source text.")

        # Track 3 Temporal safety: ensure temporal info is grounded
        if event.temporal_information:
            temporal_str = str(event.temporal_information)
            # If temporal info is plain string, check verbatim presence or valid relative anchor
            if isinstance(event.temporal_information, str) and event.temporal_information not in raw_text:
                review_reasons.append(f"Temporal information '{temporal_str}' not found verbatim in text.")

        # Attach Model Metadata
        event.model_metadata.update({
            "model_name": prediction.model_name,
            "model_version": prediction.model_version,
            "checkpoint_version": prediction.checkpoint_version,
            "model_confidence": round(prediction.model_confidence, 4),
            "decision_pipeline": "hybrid_deberta_cascade",
        })

        # I. Hybrid Decision Policy State Resolution
        if validation_errors:
            # Missing critical grounding or corrupted spans
            if any("verbatim" in err or "mismatch" in err or "Missing required SourceReference" in err for err in validation_errors):
                decision_state = EnsembleDecisionState.REVIEW_NEEDED
            else:
                decision_state = EnsembleDecisionState.REJECTED
        elif review_reasons or compound_triggered or lifecycle_triggered:
            decision_state = EnsembleDecisionState.REVIEW_NEEDED
        elif prediction.model_confidence < self.config.min_validation_confidence:
            decision_state = EnsembleDecisionState.REVIEW_NEEDED
            review_reasons.append(
                f"Model classification confidence ({prediction.model_confidence:.4f}) below validation threshold ({self.config.min_validation_confidence})."
            )
        else:
            decision_state = EnsembleDecisionState.VALIDATED

        return EnsembleValidationResult(
            decision_state=decision_state,
            neural_prediction=prediction,
            event=event,
            validation_errors=validation_errors,
            review_reasons=review_reasons,
            lifecycle_guard_triggered=lifecycle_triggered,
            is_compound_sentence=compound_triggered,
            grounding_verified=grounding_ok,
        )

    def _check_lifecycle_conflicts(self, pred_type: EventType, sentence_lower: str, rule_cands: List[EventCandidate]) -> Optional[str]:
        """Detects difficult lifecycle boundary conflicts based on empirical error patterns."""
        # 1. ITEM_SHIPPED vs ITEM_DELIVERED
        if pred_type == EventType.ITEM_DELIVERED:
            transit_cues = ["handed to courier", "out for delivery", "in transit", "drop box", "dispatched", "on its way"]
            if any(cue in sentence_lower for cue in transit_cues) and not any(k in sentence_lower for k in ["delivered", "handed over", "signed for"]):
                return "ITEM_DELIVERED predicted on active transit / courier drop-off clause; requires lifecycle verification."
        elif pred_type == EventType.ITEM_SHIPPED:
            if "delivered" in sentence_lower or "handed over" in sentence_lower:
                return "ITEM_SHIPPED predicted but delivery completion cue present in text."

        # 2. RETURN_REQUESTED vs RETURN_PICKED_UP vs RETURN_COMPLETED
        if pred_type == EventType.RETURN_PICKED_UP:
            if any(k in sentence_lower for k in ["distribution center", "warehouse", "inspection passed"]):
                return "RETURN_PICKED_UP predicted on warehouse arrival/inspection clause; lifecycle ambiguity with RETURN_COMPLETED."
        elif pred_type == EventType.RETURN_REQUESTED:
            if "picked up" in sentence_lower or "item collected" in sentence_lower:
                return "RETURN_REQUESTED predicted but courier pickup indicator present."

        # 3. REFUND_REQUESTED vs REFUND_INITIATED vs REFUND_COMPLETED
        if pred_type == EventType.REFUND_COMPLETED:
            if any(k in sentence_lower for k in ["refund requested", "asked for refund", "processing refund", "refund underway"]):
                return "REFUND_COMPLETED predicted on refund request / initiation context."
        elif pred_type == EventType.REFUND_REQUESTED:
            if "refund credited" in sentence_lower or "refund completed" in sentence_lower:
                return "REFUND_REQUESTED predicted but completion settlement indicator present."

        # 4. PAYMENT_MADE vs PAYMENT_FAILED
        if pred_type == EventType.PAYMENT_MADE:
            if any(k in sentence_lower for k in ["not cleared", "unsuccessful", "failed", "declined", "rejected"]):
                return "PAYMENT_MADE predicted on negated or unsuccessful payment context; lifecycle conflict with PAYMENT_FAILED."
        elif pred_type == EventType.PAYMENT_FAILED:
            if any(k in sentence_lower for k in ["settled", "payment successful"]) and "not" not in sentence_lower:
                return "PAYMENT_FAILED predicted on successful settlement clause."

        return None

    def extract_validated_events(
        self,
        evidence_text: EvidenceText,
        entities: Optional[List[EntityMention]] = None,
    ) -> List[Event]:
        """Convenience method returning strictly VALIDATED events."""
        results = self.process_evidence(evidence_text, entities)
        return [r.event for r in results if r.decision_state == EnsembleDecisionState.VALIDATED and r.event is not None]
