from decimal import Decimal
from ml.entities.deterministic import DeterministicExtractor
from ml.schemas.entity import EntityType


def test_extract_monetary_amounts():
    extractor = DeterministicExtractor()
    text = "Payment received for INR 10,000.00 and $45.50. Another payment of ₹1,50,000 settled."
    spans = extractor.extract_spans(text)
    money_spans = [s for s in spans if s.entity_type == EntityType.MONETARY_AMOUNT]
    assert len(money_spans) == 3
    raw_vals = [s.raw_value for s in money_spans]
    assert any("INR 10,000.00" in v for v in raw_vals)
    assert any("$45.50" in v or "$ 45.50" in v for v in raw_vals)
    assert any("₹1,50,000" in v for v in raw_vals)


def test_extract_domain_identifiers():
    extractor = DeterministicExtractor()
    text = "Order ORD-98421 generated Invoice INV-2026-0042. Transaction TXN-88120 refund RFD-55120."
    spans = extractor.extract_spans(text)

    types = {s.entity_type for s in spans}
    assert EntityType.ORDER_ID in types
    assert EntityType.INVOICE_ID in types
    assert EntityType.TRANSACTION_ID in types
    assert EntityType.REFUND_ID in types

    order = next(s for s in spans if s.entity_type == EntityType.ORDER_ID)
    assert "ORD-98421" in order.raw_value


def test_extract_contact_and_urls():
    extractor = DeterministicExtractor()
    text = "Contact support@acmestore.com or visit https://acmestore.com/faq. Helpline: +91 9876543210."
    spans = extractor.extract_spans(text)

    emails = [s for s in spans if s.entity_type == EntityType.EMAIL]
    assert len(emails) == 1
    assert emails[0].raw_value == "support@acmestore.com"

    urls = [s for s in spans if s.entity_type == EntityType.URL]
    assert len(urls) == 1
    assert urls[0].raw_value == "https://acmestore.com/faq"

    phones = [s for s in spans if s.entity_type == EntityType.PHONE_NUMBER]
    assert len(phones) == 1
    assert "+91 9876543210" in phones[0].raw_value
