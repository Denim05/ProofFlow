from decimal import Decimal
from ml.entities.deterministic import RawEntitySpan
from ml.entities.normalizer import EntityNormalizer
from ml.schemas.entity import EntityType, MonetaryValue, PhoneNumberValue


def test_normalize_money_to_exact_decimal():
    normalizer = EntityNormalizer()
    span = RawEntitySpan(
        entity_type=EntityType.MONETARY_AMOUNT,
        raw_value="₹ 1,50,000.50",
        char_start=0,
        char_end=13,
        metadata={"currency_raw": "₹", "amount_raw": "1,50,000.50"},
    )
    norm = normalizer.normalize(span)
    assert isinstance(norm, MonetaryValue)
    assert norm.currency == "INR"
    assert isinstance(norm.value, Decimal)
    assert norm.value == Decimal("150000.50")


def test_normalize_phone_unanchored_vs_anchored():
    normalizer = EntityNormalizer()
    # Unanchored local phone
    span_local = RawEntitySpan(
        entity_type=EntityType.PHONE_NUMBER,
        raw_value="9876543210",
        char_start=0,
        char_end=10,
        metadata={"digits_only": "9876543210", "has_international_prefix": False},
    )
    norm_local = normalizer.normalize(span_local, country_context=None)
    assert isinstance(norm_local, PhoneNumberValue)
    assert norm_local.country_code == "UNKNOWN"
    assert norm_local.e164_formatted is None

    # Anchored with country context
    norm_anchored = normalizer.normalize(span_local, country_context="+91")
    assert isinstance(norm_anchored, PhoneNumberValue)
    assert norm_anchored.country_code == "+91"
    assert norm_anchored.e164_formatted == "+919876543210"

    # Explicit international prefix in raw
    span_intl = RawEntitySpan(
        entity_type=EntityType.PHONE_NUMBER,
        raw_value="+1 5551234567",
        char_start=0,
        char_end=13,
        metadata={"digits_only": "15551234567", "has_international_prefix": True, "country_prefix": "1"},
    )
    norm_intl = normalizer.normalize(span_intl)
    assert norm_intl.country_code == "+1"
    assert norm_intl.e164_formatted == "+15551234567"
