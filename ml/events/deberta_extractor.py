"""Fine-tuned DeBERTa-v3 Event Extractor for ProofFlow.

Combines neural sequence prediction with Track 3 spatial entity grounding
to generate strictly grounded, provenance-traceable Event instances.
"""

import os
import sys
from typing import Any, Dict, List, Optional

os.environ.setdefault("HF_HOME", os.path.abspath(".cache/huggingface"))

import torch

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from ml.entities.pipeline import EntityExtractionPipeline
from ml.events.config import EventExtractionConfig, event_config
from ml.events.deberta_config import DebertaEventConfig, default_deberta_config, detect_execution_device
from ml.events.detector import EventCandidate, EventDetector
from ml.events.extractor import EventArgumentExtractor
from ml.schemas.event import (
    Event,
    EventModality,
    EventPolarity,
    EventTaxonomyVersion,
    EventTense,
    EventTrigger,
    EventType,
)
from ml.schemas.evidence_text import EvidenceText
from ml.schemas.source_reference import SourceReference


class DebertaEventExtractor:
    """Neural event extractor utilizing fine-tuned DeBERTa-v3 with Track 3 entity slot binding."""

    def __init__(
        self,
        checkpoint_dir: str = "ml/checkpoints/deberta_v3_event",
        config: DebertaEventConfig = default_deberta_config,
        extraction_config: EventExtractionConfig = event_config,
        entity_pipeline: Optional[EntityExtractionPipeline] = None,
    ):
        self.checkpoint_dir = checkpoint_dir
        self.config = config
        self.extraction_config = extraction_config
        self.arg_extractor = EventArgumentExtractor(extraction_config)
        self.rule_detector = EventDetector(extraction_config)
        self.entity_pipeline = entity_pipeline or EntityExtractionPipeline()

        self.device_info = detect_execution_device()
        self.device = torch.device(self.device_info["selected_device"])

        self.model = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self):
        """Loads fine-tuned model and tokenizer if available."""
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if os.path.exists(self.checkpoint_dir):
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(self.checkpoint_dir)
                self.model = AutoModelForSequenceClassification.from_pretrained(self.checkpoint_dir)
                self.model.to(self.device)
                self.model.eval()
            except Exception as e:
                print(f"Warning: Failed to load checkpoint from {self.checkpoint_dir}: {e}")
                self.model = None
                self.tokenizer = None
        else:
            self.model = None
            self.tokenizer = None

    def extract_events_from_evidence(
        self,
        evidence_text: EvidenceText,
        entity_mentions: Optional[List[Any]] = None,
    ) -> List[Event]:
        """Extracts grounded events from EvidenceText using fine-tuned DeBERTa and entity mentions."""
        if not evidence_text.full_normalized_text or not self.model or not self.tokenizer:
            return []

        if entity_mentions is None:
            entity_mentions = self.entity_pipeline.process_evidence_text(evidence_text)

        full_text = evidence_text.full_normalized_text
        sentences = self.rule_detector._split_into_sentences_with_offsets(full_text)
        extracted_events: List[Event] = []

        for s_text, s_start, s_end in sentences:
            if not s_text.strip():
                continue

            # 1. Neural classification
            encoding = self.tokenizer(
                s_text,
                truncation=True,
                max_length=self.config.max_seq_length,
                return_tensors="pt",
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**encoding)
                probs = torch.softmax(outputs.logits, dim=1).squeeze(0)
                pred_idx = torch.argmax(probs).item()
                confidence = float(probs[pred_idx].item())

            pred_label = self.config.id2label.get(pred_idx, "NO_EVENT")
            if pred_label == "NO_EVENT":
                continue

            # Validate that the predicted label is an official EventType
            try:
                event_type = EventType(pred_label)
            except ValueError:
                continue

            # 2. Trigger Span refinement
            # Find the best representative trigger in the sentence matching the event
            trig_raw = s_text
            trig_start = s_start
            trig_end = s_end

            # Check rule candidates for fine-grained sub-span anchor
            rule_cands = self.rule_detector.detect_candidates(s_text)
            matched_cand = next((c for c in rule_cands if c.event_type == event_type), None)
            if matched_cand:
                trig_raw = matched_cand.trigger_text
                trig_start = s_start + matched_cand.char_start
                trig_end = s_start + matched_cand.char_end

            # Analyze sentence nuances
            polarity, modality, tense = self.rule_detector._analyze_sentence_nuances(
                s_text.lower(),
                max(0, trig_start - s_start),
                max(0, trig_end - s_start),
            )

            candidate = EventCandidate(
                event_type=event_type,
                trigger_text=trig_raw,
                char_start=trig_start,
                char_end=trig_end,
                polarity=polarity,
                modality=modality,
                tense=tense,
                confidence=confidence,
                context_sentence=s_text,
                context_start=s_start,
                context_end=s_end,
            )

            event = self.arg_extractor.bind_arguments_to_event(
                candidate=candidate,
                evidence_text=evidence_text,
                entities=entity_mentions,
            )

            event.confidence = float(confidence)
            event.model_metadata.update({
                "extractor": "fine_tuned_deberta_v3",
                "model_name": self.config.model_name,
                "checkpoint": self.checkpoint_dir,
                "device": self.device_info["selected_device"],
                "gpu_name": self.device_info["gpu_name"],
                "vram_gb": self.device_info["vram_gb"],
                "neural_confidence": round(confidence, 4),
            })
            extracted_events.append(event)

        return extracted_events
