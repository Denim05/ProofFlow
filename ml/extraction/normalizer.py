import unicodedata
from typing import List, Tuple
from ml.schemas.evidence_text import OffsetMapEntry

ZERO_WIDTH_CHARS = {
    "\u200b",  # Zero-width space
    "\u200c",  # Zero-width non-joiner
    "\u200d",  # Zero-width joiner
    "\ufeff",  # Zero-width no-break space / BOM
}


class TextNormalizer:
    """Normalizes text while computing an explicit bidirectional character offset mapping.

    Downstream extractors can accurately translate normalized character spans back to raw source offsets.
    """

    @staticmethod
    def normalize_with_offsets(raw_text: str) -> Tuple[str, List[OffsetMapEntry]]:
        """Applies Unicode NFC normalization and strips invisible zero-width glyphs,

        recording precise boundary mappings between normalized and raw indices.
        """
        # Step 1: Character-level pass tracking raw index correspondence
        # Each entry in aligned_chars is (normalized_char_or_chars, original_raw_index)
        normalized_chars: List[str] = []
        raw_indices: List[int] = []

        i = 0
        while i < len(raw_text):
            char = raw_text[i]

            # Normalize Windows line endings \r\n to single \n
            if char == "\r" and i + 1 < len(raw_text) and raw_text[i + 1] == "\n":
                normalized_chars.append("\n")
                raw_indices.append(i)  # Maps to start of \r\n
                i += 2
                continue
            elif char == "\r":
                normalized_chars.append("\n")
                raw_indices.append(i)
                i += 1
                continue

            # Skip invisible zero-width characters (do not output to normalized stream)
            if char in ZERO_WIDTH_CHARS:
                i += 1
                continue

            # NFC normalize character (may expand or remain single char)
            nfc_char = unicodedata.normalize("NFC", char)
            for sub_char in nfc_char:
                normalized_chars.append(sub_char)
                raw_indices.append(i)

            i += 1

        norm_text = "".join(normalized_chars)

        # Step 2: Build segmented chunk mappings for efficient serialization
        offset_mapping: List[OffsetMapEntry] = []
        if not norm_text:
            return "", []

        chunk_size = 50  # 50-character interval boundaries
        for start_norm in range(0, len(norm_text), chunk_size):
            end_norm = min(start_norm + chunk_size, len(norm_text))
            raw_start = raw_indices[start_norm]
            # raw_end is the index right after the raw index of the last character in the slice
            raw_end = raw_indices[end_norm - 1] + 1
            offset_mapping.append(
                OffsetMapEntry(
                    norm_start=start_norm,
                    norm_end=end_norm,
                    raw_start=raw_start,
                    raw_end=raw_end,
                )
            )

        return norm_text, offset_mapping

    @staticmethod
    def map_span_to_raw(
        norm_start: int,
        norm_end: int,
        raw_text: str,
        norm_text: str,
    ) -> Tuple[int, int]:
        """Resolves the precise raw [start, end) span corresponding to a normalized [start, end) span."""
        if norm_start >= len(norm_text) or norm_end > len(norm_text):
            raise IndexError("Normalized indices out of bounds")

        # Re-derive exact index mapping for query
        _, offset_entries = TextNormalizer.normalize_with_offsets(raw_text)

        # High-resolution direct index lookup
        # Step through character by character to guarantee exact byte boundary
        norm_idx = 0
        raw_idx = 0
        raw_target_start = 0
        raw_target_end = len(raw_text)

        i = 0
        n_idx = 0
        while i < len(raw_text) and n_idx < len(norm_text):
            char = raw_text[i]
            if char in ZERO_WIDTH_CHARS:
                i += 1
                continue
            if char == "\r" and i + 1 < len(raw_text) and raw_text[i + 1] == "\n":
                if n_idx == norm_start:
                    raw_target_start = i
                if n_idx + 1 == norm_end:
                    raw_target_end = i + 2
                    break
                i += 2
                n_idx += 1
                continue
            elif char == "\r":
                if n_idx == norm_start:
                    raw_target_start = i
                if n_idx + 1 == norm_end:
                    raw_target_end = i + 1
                    break
                i += 1
                n_idx += 1
                continue

            nfc = unicodedata.normalize("NFC", char)
            if n_idx == norm_start:
                raw_target_start = i
            n_idx += len(nfc)
            if n_idx >= norm_end and raw_target_end == len(raw_text):
                raw_target_end = i + 1
                break
            i += 1

        return raw_target_start, min(raw_target_end, len(raw_text))
