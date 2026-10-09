from typing import Dict, List
from ml.schemas.event import EventCategory, EventType, EventTaxonomyVersion

TAXONOMY_VERSION = EventTaxonomyVersion.V1_0

# Event Categories and their associated EventTypes
EVENT_CATEGORY_MAP: Dict[EventCategory, List[EventType]] = {
    EventCategory.COMMERCE: [
        EventType.ORDER_PLACED,
        EventType.PAYMENT_MADE,
        EventType.PAYMENT_FAILED,
        EventType.REFUND_REQUESTED,
        EventType.REFUND_INITIATED,
        EventType.REFUND_COMPLETED,
        EventType.REFUND_FAILED,
    ],
    EventCategory.ORDER_DELIVERY: [
        EventType.ORDER_CANCELLED,
        EventType.ITEM_SHIPPED,
        EventType.DELIVERY_ATTEMPTED,
        EventType.ITEM_DELIVERED,
        EventType.RETURN_REQUESTED,
        EventType.RETURN_PICKED_UP,
        EventType.RETURN_COMPLETED,
    ],
    EventCategory.COMMUNICATION: [
        EventType.MESSAGE_SENT,
        EventType.MESSAGE_RECEIVED,
        EventType.SUPPORT_CONTACTED,
        EventType.SUPPORT_RESPONSE,
    ],
}

# Canonical Trigger Phrase dictionaries for deterministic detection
TRIGGER_LEXICON: Dict[EventType, List[str]] = {
    # Commerce
    EventType.ORDER_PLACED: [
        "order placed", "placed order", "order confirmed", "order received",
        "purchased", "checkout completed", "bought", "booking confirmed",
    ],
    EventType.PAYMENT_MADE: [
        "payment successful", "payment received", "paid", "amount debited",
        "debited", "payment settled", "payment processed", "payment of",
    ],
    EventType.PAYMENT_FAILED: [
        "payment failed", "payment unsuccessful", "transaction failed",
        "payment declined", "transaction declined", "payment rejected",
    ],
    EventType.REFUND_REQUESTED: [
        "refund requested", "requested a refund", "asked for refund",
        "demanded refund", "claim for refund", "refund application",
    ],
    EventType.REFUND_INITIATED: [
        "refund initiated", "refund in progress", "processing refund",
        "refund underway", "refund started",
    ],
    EventType.REFUND_COMPLETED: [
        "refund completed", "refund credited", "refund settled",
        "refund processed", "amount refunded", "refund successful", "money refunded",
    ],
    EventType.REFUND_FAILED: [
        "refund failed", "refund rejected", "refund declined", "refund denied",
    ],

    # Order / Delivery
    EventType.ORDER_CANCELLED: [
        "order cancelled", "cancelled order", "cancellation confirmed", "order voided",
    ],
    EventType.ITEM_SHIPPED: [
        "shipped", "order shipped", "item dispatched", "dispatched",
        "in transit", "out for delivery", "handed to courier",
    ],
    EventType.DELIVERY_ATTEMPTED: [
        "delivery attempted", "attempted delivery", "delivery failed",
        "recipient unavailable", "could not deliver",
    ],
    EventType.ITEM_DELIVERED: [
        "delivered", "item delivered", "order delivered", "package delivered",
        "delivery completed", "handed over",
    ],
    EventType.RETURN_REQUESTED: [
        "return requested", "requested return", "return initiated",
        "replacement requested",
    ],
    EventType.RETURN_PICKED_UP: [
        "return picked up", "item collected", "package collected",
        "pickup completed", "return package handed",
    ],
    EventType.RETURN_COMPLETED: [
        "return completed", "return received at warehouse", "return inspection passed",
        "return accepted",
    ],

    # Communication
    EventType.MESSAGE_SENT: [
        "message sent", "sent message", "wrote to", "emailed", "sent email",
    ],
    EventType.MESSAGE_RECEIVED: [
        "message received", "received message", "got email", "received email",
    ],
    EventType.SUPPORT_CONTACTED: [
        "contacted support", "raised ticket", "contacted customer service",
        "opened support ticket", "reached out to support", "called helpline",
    ],
    EventType.SUPPORT_RESPONSE: [
        "support responded", "agent replied", "support reply",
        "customer service replied", "ticket updated",
    ],
}
