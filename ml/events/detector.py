import re
from typing import List, Optional, Tuple
from ml.events.config import EventExtractionConfig, event_config
from ml.events.taxonomy import TRIGGER_LEXICON
from ml.schemas.event import EventModality, EventPolarity, EventTense, EventType

DISCLAIMER_PATTERNS = [
    r"\bshould\s+not\s+be\s+(?:treated|taken|considered)\s+(?:as\s+)?proof\b",
    r"\bdoes\s+not\s+(?:[A-Za-z]+\s+)?(?:constitute|establish|prove)\b",
    r"\bnot\s+(?:to\s+be\s+treated\s+as\s+|a\s+)?proof\s+(?:that|of)\b",
    r"\bnot\s+evidence\s+(?:that|of)\b",
    r"\b(?:simulated|fictional)\s+(?:status|record|document|transcript|customer claim)\b",
    r"\bfor\s+(?:testing|demonstration|simulation)\s+purposes\s+only\b",
]


class EventCandidate:
    """Detected event candidate anchored to a trigger span in text."""

    def __init__(
        self,
        event_type: EventType,
        trigger_text: str,
        char_start: int,
        char_end: int,
        polarity: EventPolarity = EventPolarity.POSITIVE,
        modality: EventModality = EventModality.ASSERTED,
        tense: EventTense = EventTense.PAST,
        confidence: float = 0.95,
        context_sentence: str = "",
        context_start: int = 0,
        context_end: int = 0,
    ):
        self.event_type = event_type
        self.trigger_text = trigger_text
        self.char_start = char_start
        self.char_end = char_end
        self.polarity = polarity
        self.modality = modality
        self.tense = tense
        self.confidence = confidence
        self.context_sentence = context_sentence
        self.context_start = context_start
        self.context_end = context_end


class EventDetector:
    """Deterministic event trigger detector analyzing negation, modality, and tense."""

    def __init__(self, config: EventExtractionConfig = event_config):
        self.config = config
        self._compiled_triggers = self._compile_triggers()

    def _compile_triggers(self):
        compiled = {}
        for etype, triggers in TRIGGER_LEXICON.items():
            pattern_parts = []
            # Sort by descending length so multi-word triggers are prioritized
            sorted_trigs = sorted(triggers, key=len, reverse=True)
            for trig in sorted_trigs:
                tokens = trig.strip().split()
                if len(tokens) == 1:
                    pattern_parts.append(r"\b" + re.escape(tokens[0]) + r"\b")
                else:
                    # Allow up to 8 intervening tokens (including monetary amounts, order IDs, auxiliaries)
                    intervening = r"(?:\s+\S+){0,8}\s+"
                    part = r"\b" + intervening.join(re.escape(tok) for tok in tokens) + r"\b"
                    pattern_parts.append(part)
            pattern_str = r"(?:" + "|".join(pattern_parts) + r")"
            compiled[etype] = re.compile(pattern_str, re.IGNORECASE)
        return compiled

    def detect_candidates(self, text: str) -> List[EventCandidate]:
        """Detects event candidates across text while analyzing polarity and modality in context."""
        if not text:
            return []

        candidates: List[EventCandidate] = []
        sentences = self._split_into_sentences_with_offsets(text)

        for s_text, s_start, s_end in sentences:
            s_lower = s_text.lower()

            # Disclaimers must not produce affirmative event candidates
            if any(re.search(pat, s_lower) for pat in DISCLAIMER_PATTERNS):
                continue

            for etype, regex in self._compiled_triggers.items():
                for m in regex.finditer(s_text):
                    t_start = s_start + m.start()
                    t_end = s_start + m.end()
                    t_raw = m.group(0)

                    # Analyze linguistic nuances in the sentence context
                    polarity, modality, tense = self._analyze_sentence_nuances(s_lower, m.start(), m.end())

                    # Extraction confidence calculation
                    conf = 0.95
                    if modality != EventModality.ASSERTED:
                        conf = 0.90
                    if polarity == EventPolarity.NEGATED:
                        conf = 0.92

                    candidates.append(
                        EventCandidate(
                            event_type=etype,
                            trigger_text=t_raw,
                            char_start=t_start,
                            char_end=t_end,
                            polarity=polarity,
                            modality=modality,
                            tense=tense,
                            confidence=conf,
                            context_sentence=s_text,
                            context_start=s_start,
                            context_end=s_end,
                        )
                    )

        # Remove redundant overlaps preferring longer trigger spans
        return self._deduplicate_candidates(candidates)

    def _analyze_sentence_nuances(
        self,
        sentence_lower: str,
        trig_start_in_s: int,
        trig_end_in_s: int,
    ) -> Tuple[EventPolarity, EventModality, EventTense]:
        """Determines whether trigger is negated, conditional, modal/uncertain, or future."""
        prefix_window = sentence_lower[:trig_start_in_s]
        suffix_window = sentence_lower[trig_end_in_s:]
        trig_window = sentence_lower[trig_start_in_s:trig_end_in_s]

        # 1. Check Negation
        is_negated = False

        # Check disclaimer negation
        if any(re.search(pat, sentence_lower) for pat in DISCLAIMER_PATTERNS):
            is_negated = True
        
        # Check inside trigger span first
        for n_cue in self.config.negation_cues:
            if re.search(rf"\b{re.escape(n_cue)}\b", trig_window):
                is_negated = True
                break

        # Check prefix window (bounded to immediate clause before trigger)
        if not is_negated:
            pre_clause = re.split(r"[,;]|\b(?:and|but)\b", prefix_window)[-1]
            for n_cue in self.config.negation_cues:
                if re.search(rf"\b{re.escape(n_cue)}\b", pre_clause):
                    is_negated = True
                    break

        # Check suffix window (immediately following trigger e.g. ": no")
        if not is_negated:
            for n_cue in self.config.negation_cues:
                if re.search(rf"^[\s:,\-]+{re.escape(n_cue)}\b", suffix_window):
                    is_negated = True
                    break

        # 2. Check Conditional ("if approved", "subject to", "provided that")
        is_conditional = False
        for c_cue in self.config.conditional_cues:
            if re.search(rf"\b{re.escape(c_cue)}\b", sentence_lower):
                is_conditional = True
                break

        # 3. Check Modal / Uncertain ("may be completed", "might arrive")
        is_uncertain = False
        for m_cue in self.config.modal_cues:
            if re.search(rf"\b{re.escape(m_cue)}\b", sentence_lower):
                is_uncertain = True
                break

        # 4. Check Future / Tense ("will be completed tomorrow", "scheduled to ship")
        is_future = False
        for f_cue in self.config.future_cues:
            if re.search(rf"\b{re.escape(f_cue)}\b", sentence_lower):
                is_future = True
                break

        polarity = EventPolarity.NEGATED if is_negated else EventPolarity.POSITIVE

        # Modality priority: CONDITIONAL > UNCERTAIN > PLANNED > ASSERTED
        if is_conditional:
            modality = EventModality.CONDITIONAL
        elif is_uncertain:
            modality = EventModality.UNCERTAIN
        elif is_future:
            modality = EventModality.PLANNED
        else:
            modality = EventModality.ASSERTED

        tense = EventTense.FUTURE if is_future else EventTense.PAST

        return polarity, modality, tense

    def _split_into_sentences_with_offsets(self, text: str) -> List[Tuple[str, int, int]]:
        """Splits text into sentence fragments while preserving global character offsets.
        
        Ensures decimal numbers (e.g. INR 2,499.50 or $45.50) are not split mid-token.
        """
        sentence_end_re = re.compile(
            r"((?<!\d)\.(?!\d)(?:\s+|$)|(?<=\d)\.\s+(?=[A-Za-z])|[!?]+(?:\s+|$)|(?:\r?\n\s*){2,}|(?:\r?\n(?!\s*[a-z])))"
        )
        sentences: List[Tuple[str, int, int]] = []
        start = 0

        for match in sentence_end_re.finditer(text):
            end = match.end()
            chunk = text[start:end].strip()
            if chunk:
                chunk_start = text.find(chunk, start)
                chunk_end = chunk_start + len(chunk)
                sentences.append((chunk, chunk_start, chunk_end))
            start = end

        if start < len(text):
            remaining = text[start:].strip()
            if remaining:
                chunk_start = text.find(remaining, start)
                chunk_end = chunk_start + len(remaining)
                sentences.append((remaining, chunk_start, chunk_end))

        if not sentences and text.strip():
            sentences.append((text.strip(), 0, len(text)))

        return sentences

    def _deduplicate_candidates(self, candidates: List[EventCandidate]) -> List[EventCandidate]:
        """Resolves overlapping candidates by preferring longer trigger spans."""
        sorted_cands = sorted(
            candidates,
            key=lambda c: (-(c.char_end - c.char_start), c.char_start),
        )
        final: List[EventCandidate] = []
        for c in sorted_cands:
            if not any(max(c.char_start, ex.char_start) < min(c.char_end, ex.char_end) for ex in final):
                final.append(c)
        return sorted(final, key=lambda c: c.char_start)
