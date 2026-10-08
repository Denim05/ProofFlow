from ml.entities.temporal import TemporalExtractor
from ml.schemas.entity import EntityType


def test_extract_unambiguous_dates():
    extractor = TemporalExtractor()
    text = "Payment on 2026-10-07 and statement issued on October 7, 2026."
    spans = extractor.extract_temporal_spans(text)

    date_spans = [s for s in spans if s.entity_type == EntityType.DATE]
    assert len(date_spans) == 2
    for s in date_spans:
        assert s.metadata.get("iso_date") == "2026-10-07"
        assert s.metadata.get("is_ambiguous") is False


def test_preserve_ambiguous_date():
    extractor = TemporalExtractor()
    # 04/05/2026 could be April 5 or May 4 -> Ambiguous!
    text = "Document dated 04/05/2026."
    spans = extractor.extract_temporal_spans(text)

    date_spans = [s for s in spans if s.entity_type == EntityType.DATE]
    assert len(date_spans) == 1
    assert date_spans[0].metadata.get("is_ambiguous") is True
    assert date_spans[0].metadata.get("iso_date") is None
    assert len(date_spans[0].metadata.get("candidate_dates")) == 2


def test_extract_times():
    extractor = TemporalExtractor()
    text = "Action logged at 14:30:00 and repeated at 2:30 PM."
    spans = extractor.extract_temporal_spans(text)

    time_spans = [s for s in spans if s.entity_type == EntityType.TIME]
    assert len(time_spans) == 2
    assert time_spans[0].metadata.get("norm_time") == "14:30:00"
    assert time_spans[1].metadata.get("norm_time") == "14:30:00"


def test_relative_time_with_and_without_anchor():
    extractor = TemporalExtractor()
    text = "Message sent yesterday."

    # 1. Without anchor -> UNRESOLVED_NO_ANCHOR
    spans_no_anchor = extractor.extract_temporal_spans(text, document_anchor=None)
    rel_span = next(s for s in spans_no_anchor if s.entity_type == EntityType.RELATIVE_TIME)
    res = rel_span.metadata["relative_resolution"]
    assert res.resolution_status == "UNRESOLVED_NO_ANCHOR"
    assert res.computed_value is None

    # 2. With anchored header -> RESOLVED_WITH_ANCHOR
    anchor = {"anchor_date": "2026-10-08T10:00:00Z", "source": "chat_header"}
    spans_with_anchor = extractor.extract_temporal_spans(text, document_anchor=anchor)
    rel_span_anchored = next(s for s in spans_with_anchor if s.entity_type == EntityType.RELATIVE_TIME)
    res_anchored = rel_span_anchored.metadata["relative_resolution"]
    assert res_anchored.resolution_status == "RESOLVED_WITH_ANCHOR"
    assert res_anchored.computed_value == "2026-10-07"
