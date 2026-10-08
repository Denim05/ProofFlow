from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List, Optional, Tuple
from ml.entities.deterministic import RawEntitySpan
from ml.schemas.entity import EntityType, RelativeTimeResolution


class TemporalExtractor:
    """Extracts Date, Time, DateTime, and RelativeTime spans with strict anchor safety."""

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        # 1. Unambiguous ISO Date: YYYY-MM-DD or YYYY/MM/DD
        self.iso_date_re = re.compile(
            r"\b(?P<year>20\d\d|19\d\d)[-/](?P<month>0[1-9]|1[0-2])[-/](?P<day>0[1-9]|[12]\d|3[01])\b"
        )

        # 2. Word Month Dates: "October 7, 2026", "7 October 2026", "07-Oct-2026", "Oct 7 2026"
        months = (
            r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        )
        self.word_date_re1 = re.compile(
            rf"\b(?P<month>{months})\s+(?P<day>[0-3]?\d)(?:st|nd|rd|th)?,?\s+(?P<year>20\d\d|19\d\d)\b",
            re.IGNORECASE,
        )
        self.word_date_re2 = re.compile(
            rf"\b(?P<day>[0-3]?\d)(?:st|nd|rd|th)?[\s\-_]+(?P<month>{months})[\s\-_]+(?P<year>20\d\d|19\d\d)\b",
            re.IGNORECASE,
        )

        # 3. Numeric slash/dash dates (potentially ambiguous e.g. 04/05/2026 vs 25/12/2026)
        self.numeric_date_re = re.compile(
            r"\b(?P<part1>[0-3]?\d)[-/](?P<part2>[0-3]?\d)[-/](?P<year>20\d\d|19\d\d)\b"
        )

        # 4. Clock Times: 14:30:00, 2:30 PM, 10:15 am
        self.time_re = re.compile(
            r"\b(?P<hour>[01]?\d|2[0-3]):(?P<min>[0-5]\d)(?::(?P<sec>[0-5]\d))?(?:\s*(?P<meridiem>[APap][Mm]))?\b"
        )

        # 5. Relative Times: "yesterday", "today", "tomorrow", "X days ago", "X hours ago"
        self.rel_time_re = re.compile(
            r"\b(?P<rel>yesterday|today|tomorrow|just now|(?:[0-9]+|a|one|two|three|few)\s+(?:minutes?|hours?|days?|weeks?|months?)\s+ago)\b",
            re.IGNORECASE,
        )

    def extract_temporal_spans(
        self,
        text: str,
        document_anchor: Optional[Dict[str, Any]] = None,
    ) -> List[RawEntitySpan]:
        """Extracts date, time, and relative time expressions."""
        if not text:
            return []

        spans: List[RawEntitySpan] = []

        # 1. Unambiguous ISO Dates
        for m in self.iso_date_re.finditer(text):
            y, mo, d = m.group("year"), m.group("month"), m.group("day")
            norm_iso = f"{y}-{mo}-{d}"
            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.DATE,
                    raw_value=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    confidence=0.99,
                    metadata={"iso_date": norm_iso, "is_ambiguous": False},
                )
            )

        # 2. Word Month Dates
        for m in self.word_date_re1.finditer(text):
            norm_iso = self._parse_word_date(m.group("year"), m.group("month"), m.group("day"))
            if norm_iso:
                spans.append(
                    RawEntitySpan(
                        entity_type=EntityType.DATE,
                        raw_value=m.group(0),
                        char_start=m.start(),
                        char_end=m.end(),
                        confidence=0.98,
                        metadata={"iso_date": norm_iso, "is_ambiguous": False},
                    )
                )

        for m in self.word_date_re2.finditer(text):
            norm_iso = self._parse_word_date(m.group("year"), m.group("month"), m.group("day"))
            if norm_iso:
                # Avoid overlapping with re1
                if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                    spans.append(
                        RawEntitySpan(
                            entity_type=EntityType.DATE,
                            raw_value=m.group(0),
                            char_start=m.start(),
                            char_end=m.end(),
                            confidence=0.98,
                            metadata={"iso_date": norm_iso, "is_ambiguous": False},
                        )
                    )

        # 3. Numeric Dates (detecting ambiguity)
        for m in self.numeric_date_re.finditer(text):
            if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                p1 = int(m.group("part1"))
                p2 = int(m.group("part2"))
                year = m.group("year")

                # If one part > 12, interpretation is unambiguous
                if p1 > 12 and 1 <= p2 <= 12:
                    # p1 must be day, p2 must be month (DD/MM/YYYY)
                    norm_iso = f"{year}-{p2:02d}-{p1:02d}"
                    spans.append(
                        RawEntitySpan(
                            entity_type=EntityType.DATE,
                            raw_value=m.group(0),
                            char_start=m.start(),
                            char_end=m.end(),
                            confidence=0.95,
                            metadata={"iso_date": norm_iso, "is_ambiguous": False},
                        )
                    )
                elif p2 > 12 and 1 <= p1 <= 12:
                    # p2 must be day, p1 must be month (MM/DD/YYYY)
                    norm_iso = f"{year}-{p1:02d}-{p2:02d}"
                    spans.append(
                        RawEntitySpan(
                            entity_type=EntityType.DATE,
                            raw_value=m.group(0),
                            char_start=m.start(),
                            char_end=m.end(),
                            confidence=0.95,
                            metadata={"iso_date": norm_iso, "is_ambiguous": False},
                        )
                    )
                elif 1 <= p1 <= 12 and 1 <= p2 <= 12:
                    # Ambiguous (e.g. 04/05/2026: could be April 5 or May 4)
                    # Safety Rule: NEVER guess when ambiguous!
                    c1 = f"{year}-{p2:02d}-{p1:02d}"  # DD/MM
                    c2 = f"{year}-{p1:02d}-{p2:02d}"  # MM/DD
                    spans.append(
                        RawEntitySpan(
                            entity_type=EntityType.DATE,
                            raw_value=m.group(0),
                            char_start=m.start(),
                            char_end=m.end(),
                            confidence=0.75,
                            metadata={
                                "iso_date": None,
                                "is_ambiguous": True,
                                "candidate_dates": [c1, c2],
                            },
                        )
                    )

        # 4. Times
        for m in self.time_re.finditer(text):
            if not any(s.char_start <= m.start() and s.char_end >= m.end() for s in spans):
                hour = int(m.group("hour"))
                minute = int(m.group("min"))
                sec = int(m.group("sec")) if m.group("sec") else 0
                mer = m.group("meridiem")

                if mer:
                    mer_upper = mer.upper()
                    if mer_upper == "PM" and hour < 12:
                        hour += 12
                    elif mer_upper == "AM" and hour == 12:
                        hour = 0

                norm_time = f"{hour:02d}:{minute:02d}:{sec:02d}"
                spans.append(
                    RawEntitySpan(
                        entity_type=EntityType.TIME,
                        raw_value=m.group(0),
                        char_start=m.start(),
                        char_end=m.end(),
                        confidence=0.95,
                        metadata={"norm_time": norm_time},
                    )
                )

        # 5. Relative Times
        for m in self.rel_time_re.finditer(text):
            raw_rel = m.group(0)
            rel_res = self._resolve_relative_time(raw_rel, document_anchor)
            spans.append(
                RawEntitySpan(
                    entity_type=EntityType.RELATIVE_TIME,
                    raw_value=raw_rel,
                    char_start=m.start(),
                    char_end=m.end(),
                    confidence=0.90 if rel_res.resolution_status == "RESOLVED_WITH_ANCHOR" else 0.70,
                    metadata={"relative_resolution": rel_res},
                )
            )

        return spans

    def _resolve_relative_time(
        self,
        raw_text: str,
        document_anchor: Optional[Dict[str, Any]],
    ) -> RelativeTimeResolution:
        """Resolves relative time expressions strictly against a grounded in-document anchor."""
        if not document_anchor or "anchor_date" not in document_anchor:
            return RelativeTimeResolution(
                raw_text=raw_text,
                reference_anchor=None,
                computed_value=None,
                resolution_status="UNRESOLVED_NO_ANCHOR",
                resolution_confidence=0.0,
            )

        anchor_str = document_anchor["anchor_date"]
        try:
            anchor_dt = datetime.fromisoformat(anchor_str)
        except Exception:
            return RelativeTimeResolution(
                raw_text=raw_text,
                reference_anchor=document_anchor,
                computed_value=None,
                resolution_status="AMBIGUOUS_ANCHOR",
                resolution_confidence=0.0,
            )

        lower = raw_text.lower().strip()
        computed: Optional[datetime] = None

        if lower == "today":
            computed = anchor_dt
        elif lower == "yesterday":
            computed = anchor_dt - timedelta(days=1)
        elif lower == "tomorrow":
            computed = anchor_dt + timedelta(days=1)
        elif "days ago" in lower:
            num_match = re.search(r"\d+", lower)
            days = int(num_match.group(0)) if num_match else 1
            computed = anchor_dt - timedelta(days=days)
        elif "hours ago" in lower:
            num_match = re.search(r"\d+", lower)
            hours = int(num_match.group(0)) if num_match else 1
            computed = anchor_dt - timedelta(hours=hours)

        if computed:
            computed_iso = computed.date().isoformat()
            return RelativeTimeResolution(
                raw_text=raw_text,
                reference_anchor=document_anchor,
                computed_value=computed_iso,
                resolution_status="RESOLVED_WITH_ANCHOR",
                resolution_confidence=0.95,
            )

        return RelativeTimeResolution(
            raw_text=raw_text,
            reference_anchor=document_anchor,
            computed_value=None,
            resolution_status="UNRESOLVED_NO_ANCHOR",
            resolution_confidence=0.0,
        )

    def _parse_word_date(self, year_str: str, month_str: str, day_str: str) -> Optional[str]:
        month_map = {
            "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
            "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
            "nov": 11, "november": 11, "dec": 12, "december": 12,
        }
        m_num = month_map.get(month_str.lower()[:3])
        if not m_num:
            return None
        try:
            d_num = int(day_str)
            y_num = int(year_str)
            return f"{y_num:04d}-{m_num:02d}-{d_num:02d}"
        except Exception:
            return None
