"""ProofFlow Event Extraction Dataset Generator & Splitter.

Produces a versioned, balanced dataset of dispute, commerce, delivery,
and communication events with exact character spans, epistemic nuances,
and argument annotations.
"""

import json
import os
import random
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from typing import Any, Dict, List, Tuple
from ml.schemas.event import EventModality, EventPolarity, EventTense, EventType

DATASET_VERSION = "1.0.0"

# 18 Taxonomy EventTypes + 1 NO_EVENT category = 19 classification targets
ALL_EVENT_CLASSES: List[str] = [e.value for e in EventType] + ["NO_EVENT"]

LABEL2ID: Dict[str, int] = {label: idx for idx, label in enumerate(ALL_EVENT_CLASSES)}
ID2LABEL: Dict[int, str] = {idx: label for idx, label in enumerate(ALL_EVENT_CLASSES)}

RAW_SAMPLES: List[Dict[str, Any]] = [
    # --- ORDER_PLACED ---
    {
        "text": "Customer placed an order ORD-99120 for Electronics on 2026-08-10.",
        "event_type": "ORDER_PLACED",
        "trigger_text": "placed an order",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-99120", "amount": None, "temporal": "2026-08-10"
    },
    {
        "text": "Your purchase of $120.00 was confirmed for Order ORD-44019.",
        "event_type": "ORDER_PLACED",
        "trigger_text": "purchase",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-44019", "amount": "120.00", "temporal": None
    },
    {
        "text": "Order ORD-11029 placed on 2026-09-01 via online store checkout.",
        "event_type": "ORDER_PLACED",
        "trigger_text": "Order ORD-11029 placed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-11029", "amount": None, "temporal": "2026-09-01"
    },
    {
        "text": "Checkout completed successfully for order ORD-88124.",
        "event_type": "ORDER_PLACED",
        "trigger_text": "Checkout completed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-88124", "amount": None, "temporal": None
    },
    {
        "text": "User bought 2 items under booking confirmed reference ORD-70011.",
        "event_type": "ORDER_PLACED",
        "trigger_text": "booking confirmed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-70011", "amount": None, "temporal": None
    },
    {
        "text": "Order was not placed due to network timeout during cart submission.",
        "event_type": "ORDER_PLACED",
        "trigger_text": "Order was not placed",
        "polarity": "NEGATED", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "If items remain in stock, the order will be placed tomorrow.",
        "event_type": "ORDER_PLACED",
        "trigger_text": "order will be placed",
        "polarity": "POSITIVE", "modality": "CONDITIONAL", "tense": "FUTURE",
        "order_reference": None, "amount": None, "temporal": "tomorrow"
    },

    # --- PAYMENT_MADE ---
    {
        "text": "Payment received of INR 10,000.00 for Order ORD-98421 on 2026-10-07.",
        "event_type": "PAYMENT_MADE",
        "trigger_text": "Payment received",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-98421", "amount": "10000.00", "temporal": "2026-10-07"
    },
    {
        "text": "Paid $450.00 via Visa card ending in 4111 on 2026-09-15.",
        "event_type": "PAYMENT_MADE",
        "trigger_text": "Paid",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "450.00", "temporal": "2026-09-15"
    },
    {
        "text": "Amount debited of EUR 89.99 for transaction TXN-10928.",
        "event_type": "PAYMENT_MADE",
        "trigger_text": "Amount debited",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "89.99", "temporal": None
    },
    {
        "text": "Payment successful: Transaction ID: TXN-O09I82 Amount: INR 5,000.00 status: settled.",
        "event_type": "PAYMENT_MADE",
        "trigger_text": "Payment successful",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "5000.00", "temporal": None
    },
    {
        "text": "Payment of $65.00 settled successfully through PayPal.",
        "event_type": "PAYMENT_MADE",
        "trigger_text": "payment of",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "65.00", "temporal": None
    },
    {
        "text": "Payment was not received for invoice INV-4491.",
        "event_type": "PAYMENT_MADE",
        "trigger_text": "Payment was not received",
        "polarity": "NEGATED", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- PAYMENT_FAILED ---
    {
        "text": "Payment failed for transaction TXN-99120 due to insufficient funds.",
        "event_type": "PAYMENT_FAILED",
        "trigger_text": "Payment failed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Transaction declined by card issuer for attempt of $250.00.",
        "event_type": "PAYMENT_FAILED",
        "trigger_text": "Transaction declined",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "250.00", "temporal": None
    },
    {
        "text": "Payment unsuccessful: gateway timeout encountered during debit.",
        "event_type": "PAYMENT_FAILED",
        "trigger_text": "Payment unsuccessful",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Payment rejected by bank for order ORD-12903 on 2026-09-02.",
        "event_type": "PAYMENT_FAILED",
        "trigger_text": "Payment rejected",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-12903", "amount": None, "temporal": "2026-09-02"
    },

    # --- REFUND_REQUESTED ---
    {
        "text": "Buyer requested a refund of $85.00 for damaged goods on 2026-09-12.",
        "event_type": "REFUND_REQUESTED",
        "trigger_text": "requested a refund",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "85.00", "temporal": "2026-09-12"
    },
    {
        "text": "Customer demanded refund regarding missing shipment ORD-77291.",
        "event_type": "REFUND_REQUESTED",
        "trigger_text": "demanded refund",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-77291", "amount": None, "temporal": None
    },
    {
        "text": "Refund application submitted by account holder for INR 1,500.00.",
        "event_type": "REFUND_REQUESTED",
        "trigger_text": "Refund application",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "1500.00", "temporal": None
    },
    {
        "text": "Buyer asked for refund after waiting 14 days for delivery.",
        "event_type": "REFUND_REQUESTED",
        "trigger_text": "asked for refund",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- REFUND_INITIATED ---
    {
        "text": "Merchant initiated refund of $199.99 for cancelled booking ORD-33019.",
        "event_type": "REFUND_INITIATED",
        "trigger_text": "initiated refund",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-33019", "amount": "199.99", "temporal": None
    },
    {
        "text": "Refund in progress: finance team is currently processing refund of EUR 45.00.",
        "event_type": "REFUND_INITIATED",
        "trigger_text": "processing refund",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "45.00", "temporal": None
    },
    {
        "text": "Refund underway and scheduled to reflect in 3-5 business days.",
        "event_type": "REFUND_INITIATED",
        "trigger_text": "Refund underway",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Gateway started processing refund for dispute DISP-99201.",
        "event_type": "REFUND_INITIATED",
        "trigger_text": "processing refund",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- REFUND_COMPLETED ---
    {
        "text": "Refund completed successfully for Order ORD-55120 on 2026-10-01.",
        "event_type": "REFUND_COMPLETED",
        "trigger_text": "Refund completed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-55120", "amount": None, "temporal": "2026-10-01"
    },
    {
        "text": "Amount of $120.00 was credited back to customer's Mastercard.",
        "event_type": "REFUND_COMPLETED",
        "trigger_text": "refund credited",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "120.00", "temporal": None
    },
    {
        "text": "The refund of INR 2,499.50 will be completed tomorrow by customer service.",
        "event_type": "REFUND_COMPLETED",
        "trigger_text": "refund of INR 2,499.50 will be completed",
        "polarity": "POSITIVE", "modality": "PLANNED", "tense": "FUTURE",
        "order_reference": None, "amount": "2499.50", "temporal": "tomorrow"
    },
    {
        "text": "The refund was not completed due to bank rejection.",
        "event_type": "REFUND_COMPLETED",
        "trigger_text": "refund was not completed",
        "polarity": "NEGATED", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "If approved by the merchant, the refund of $45.50 will be completed for Order ORD-33100.",
        "event_type": "REFUND_COMPLETED",
        "trigger_text": "refund of $45.50 will be completed",
        "polarity": "POSITIVE", "modality": "CONDITIONAL", "tense": "FUTURE",
        "order_reference": "ORD-33100", "amount": "45.50", "temporal": None
    },
    {
        "text": "Money refunded of $78.00 back to original payment method.",
        "event_type": "REFUND_COMPLETED",
        "trigger_text": "Money refunded",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "78.00", "temporal": None
    },

    # --- REFUND_FAILED ---
    {
        "text": "Refund failed due to invalid beneficiary bank account number.",
        "event_type": "REFUND_FAILED",
        "trigger_text": "Refund failed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Refund rejected by payment processor for dispute DISP-1029.",
        "event_type": "REFUND_FAILED",
        "trigger_text": "Refund rejected",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Refund declined because transaction is past the 90-day reversal window.",
        "event_type": "REFUND_FAILED",
        "trigger_text": "Refund declined",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Refund denied: merchant policy does not allow returns on digital downloads.",
        "event_type": "REFUND_FAILED",
        "trigger_text": "Refund denied",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- ORDER_CANCELLED ---
    {
        "text": "Order cancelled by buyer before shipment dispatched.",
        "event_type": "ORDER_CANCELLED",
        "trigger_text": "Order cancelled",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Seller confirmed cancellation of order ORD-99201 on 2026-09-04.",
        "event_type": "ORDER_CANCELLED",
        "trigger_text": "cancellation confirmed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-99201", "amount": None, "temporal": "2026-09-04"
    },
    {
        "text": "Order voided due to suspected fraudulent activity on card.",
        "event_type": "ORDER_CANCELLED",
        "trigger_text": "Order voided",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Customer cancelled order ORD-55192 within the 1-hour cooling window.",
        "event_type": "ORDER_CANCELLED",
        "trigger_text": "cancelled order",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-55192", "amount": None, "temporal": None
    },

    # --- ITEM_SHIPPED ---
    {
        "text": "Item shipped by Acme Corp via FedEx on 2026-09-03.",
        "event_type": "ITEM_SHIPPED",
        "trigger_text": "Item shipped",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "2026-09-03"
    },
    {
        "text": "Package dispatched from warehouse facility under tracking TRK-88129.",
        "event_type": "ITEM_SHIPPED",
        "trigger_text": "dispatched",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Parcel is out for delivery today with local courier partner.",
        "event_type": "ITEM_SHIPPED",
        "trigger_text": "out for delivery",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "today"
    },
    {
        "text": "Consignment handed to courier at departure sorting hub.",
        "event_type": "ITEM_SHIPPED",
        "trigger_text": "handed to courier",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "The replacement parts will be shipped tomorrow morning.",
        "event_type": "ITEM_SHIPPED",
        "trigger_text": "will be shipped",
        "polarity": "POSITIVE", "modality": "PLANNED", "tense": "FUTURE",
        "order_reference": None, "amount": None, "temporal": "tomorrow"
    },

    # --- DELIVERY_ATTEMPTED ---
    {
        "text": "Delivery attempted on 2026-09-05 but customer premise was closed.",
        "event_type": "DELIVERY_ATTEMPTED",
        "trigger_text": "Delivery attempted",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "2026-09-05"
    },
    {
        "text": "Attempted delivery failed: recipient unavailable to sign for parcel.",
        "event_type": "DELIVERY_ATTEMPTED",
        "trigger_text": "Attempted delivery",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Courier could not deliver package due to incorrect street address.",
        "event_type": "DELIVERY_ATTEMPTED",
        "trigger_text": "could not deliver",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- ITEM_DELIVERED ---
    {
        "text": "Package delivered to front porch at 14:30 on 2026-09-06.",
        "event_type": "ITEM_DELIVERED",
        "trigger_text": "delivered",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "2026-09-06"
    },
    {
        "text": "Item delivered and signed for by resident on 2026-09-07.",
        "event_type": "ITEM_DELIVERED",
        "trigger_text": "Item delivered",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "2026-09-07"
    },
    {
        "text": "Delivery completed successfully at front door.",
        "event_type": "ITEM_DELIVERED",
        "trigger_text": "Delivery completed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Customer service stated that the package may be delivered by Friday.",
        "event_type": "ITEM_DELIVERED",
        "trigger_text": "delivered",
        "polarity": "POSITIVE", "modality": "UNCERTAIN", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "Friday"
    },
    {
        "text": "The ordered parcel was not delivered as tracking falsely reported.",
        "event_type": "ITEM_DELIVERED",
        "trigger_text": "was not delivered",
        "polarity": "NEGATED", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- RETURN_REQUESTED ---
    {
        "text": "Customer submitted return requested for wrong size shoe on 2026-09-14.",
        "event_type": "RETURN_REQUESTED",
        "trigger_text": "return requested",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "2026-09-14"
    },
    {
        "text": "Replacement requested for defective charger included with laptop.",
        "event_type": "RETURN_REQUESTED",
        "trigger_text": "Replacement requested",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Buyer requested return within the standard 30-day merchant warranty.",
        "event_type": "RETURN_REQUESTED",
        "trigger_text": "requested return",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- RETURN_PICKED_UP ---
    {
        "text": "Courier completed return picked up from customer residence on 2026-09-16.",
        "event_type": "RETURN_PICKED_UP",
        "trigger_text": "return picked up",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "2026-09-16"
    },
    {
        "text": "Item collected by DHL courier with pickup receipt number PU-9912.",
        "event_type": "RETURN_PICKED_UP",
        "trigger_text": "Item collected",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Return package handed to delivery agent at collection counter.",
        "event_type": "RETURN_PICKED_UP",
        "trigger_text": "return package handed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- RETURN_COMPLETED ---
    {
        "text": "Return completed: warehouse inspection passed for returned garment.",
        "event_type": "RETURN_COMPLETED",
        "trigger_text": "Return completed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Return received at warehouse and verified in good condition.",
        "event_type": "RETURN_COMPLETED",
        "trigger_text": "Return received at warehouse",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Return accepted by fulfillment team after product serial check.",
        "event_type": "RETURN_COMPLETED",
        "trigger_text": "Return accepted",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- MESSAGE_SENT ---
    {
        "text": "Buyer sent message to seller inquiring about dispatch date.",
        "event_type": "MESSAGE_SENT",
        "trigger_text": "sent message",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Customer emailed order dispute documentation on 2026-09-18.",
        "event_type": "MESSAGE_SENT",
        "trigger_text": "emailed",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": "2026-09-18"
    },
    {
        "text": "Sent email attaching proof of non-receipt to disputes department.",
        "event_type": "MESSAGE_SENT",
        "trigger_text": "Sent email",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- MESSAGE_RECEIVED ---
    {
        "text": "Buyer received email confirming cancellation of subscription.",
        "event_type": "MESSAGE_RECEIVED",
        "trigger_text": "received email",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Received message from merchant offering a $15 discount voucher.",
        "event_type": "MESSAGE_RECEIVED",
        "trigger_text": "Received message",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": "15.00", "temporal": None
    },
    {
        "text": "Got email containing return shipping label instructions.",
        "event_type": "MESSAGE_RECEIVED",
        "trigger_text": "Got email",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- SUPPORT_CONTACTED ---
    {
        "text": "I contacted support yesterday regarding Order ORD-77201.",
        "event_type": "SUPPORT_CONTACTED",
        "trigger_text": "contacted support",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": "ORD-77201", "amount": None, "temporal": "yesterday"
    },
    {
        "text": "Customer opened support ticket TKT-44129 for missing package.",
        "event_type": "SUPPORT_CONTACTED",
        "trigger_text": "opened support ticket",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Cardholder called helpline to report unauthorized debit transaction.",
        "event_type": "SUPPORT_CONTACTED",
        "trigger_text": "called helpline",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Buyer raised ticket with marketplace escalation team.",
        "event_type": "SUPPORT_CONTACTED",
        "trigger_text": "raised ticket",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- SUPPORT_RESPONSE ---
    {
        "text": "Support responded that investigation is underway with courier.",
        "event_type": "SUPPORT_RESPONSE",
        "trigger_text": "Support responded",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Agent replied to ticket stating replacement will arrive in 48 hours.",
        "event_type": "SUPPORT_RESPONSE",
        "trigger_text": "Agent replied",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Customer service replied confirming a full credit voucher was issued.",
        "event_type": "SUPPORT_RESPONSE",
        "trigger_text": "Customer service replied",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Ticket updated with latest carrier tracking investigation results.",
        "event_type": "SUPPORT_RESPONSE",
        "trigger_text": "Ticket updated",
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PAST",
        "order_reference": None, "amount": None, "temporal": None
    },

    # --- NO_EVENT (Negative non-event examples) ---
    {
        "text": "All items sold are subject to our general warranty policy terms.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "The cotton shirt features a modern cut with button-down collar.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Please retain this invoice for your personal records.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Merchant business registration number is BRN-9912048.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Thank you for shopping with Acme Retail Stores.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Opening hours are Monday to Friday 9:00 AM to 6:00 PM EST.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Deliveries to remote islands may incur additional courier surcharges.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Customer service can be reached via online live chat during business hours.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
    {
        "text": "Prices are exclusive of applicable state and local sales taxes.",
        "event_type": "NO_EVENT",
        "trigger_text": None,
        "polarity": "POSITIVE", "modality": "ASSERTED", "tense": "PRESENT",
        "order_reference": None, "amount": None, "temporal": None
    },
]


def expand_dataset(base_samples: List[Dict[str, Any]], target_size: int = 140, seed: int = 42) -> List[Dict[str, Any]]:
    """Augments and diversifies base instances to produce a balanced, realistic corpus."""
    rng = random.Random(seed)
    expanded: List[Dict[str, Any]] = []

    order_prefixes = ["ORD-", "PURCH-", "SO-", "REF-"]
    amounts = ["24.99", "59.00", "129.50", "249.99", "890.00", "1,200.00", "4,500.00"]
    dates = ["2026-08-15", "2026-09-02", "2026-09-19", "2026-10-04", "yesterday", "tomorrow"]
    couriers = ["FedEx", "UPS", "DHL", "BlueDart", "USPS"]

    # First add all original base samples
    for i, s in enumerate(base_samples):
        item = dict(s)
        item["sample_id"] = f"pf_ev_{i+1:03d}"
        expanded.append(item)

    # Now generate synthetic perturbations to reach target_size
    idx = len(expanded) + 1
    while len(expanded) < target_size:
        base = rng.choice(base_samples)
        new_item = dict(base)
        new_text = base["text"]

        # Vary order ID if present
        if base.get("order_reference"):
            new_ord = f"{rng.choice(order_prefixes)}{rng.randint(10000, 99999)}"
            new_text = new_text.replace(base["order_reference"], new_ord)
            new_item["order_reference"] = new_ord

        # Vary amount if present
        if base.get("amount"):
            new_amt = rng.choice(amounts)
            new_text = new_text.replace(base["amount"], new_amt)
            new_item["amount"] = new_amt

        # Vary date if present
        if base.get("temporal"):
            new_dt = rng.choice(dates)
            new_text = new_text.replace(base["temporal"], new_dt)
            new_item["temporal"] = new_dt

        new_item["sample_id"] = f"pf_ev_{idx:03d}"
        new_item["text"] = new_text
        expanded.append(new_item)
        idx += 1

    return expanded


def split_dataset(
    samples: List[Dict[str, Any]],
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Stratified train/val/test splitting maintaining category distributions."""
    rng = random.Random(seed)
    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for s in samples:
        by_class.setdefault(s["event_type"], []).append(s)

    train, val, test = [], [], []
    for cls_name, cls_samples in by_class.items():
        rng.shuffle(cls_samples)
        n = len(cls_samples)
        n_train = max(1, int(n * train_ratio))
        n_val = max(1, int(n * val_ratio))
        
        c_train = cls_samples[:n_train]
        c_val = cls_samples[n_train:n_train + n_val]
        c_test = cls_samples[n_train + n_val:]
        if not c_test:  # ensure held-out test has at least 1 instance per class if n >= 3
            if len(c_train) > 1:
                c_test.append(c_train.pop())

        train.extend(c_train)
        val.extend(c_val)
        test.extend(c_test)

    rng.shuffle(train)
    rng.shuffle(val)
    rng.shuffle(test)
    return train, val, test


def save_dataset_splits(output_dir: str = "ml/events/data") -> Dict[str, Any]:
    """Generates and writes train.jsonl, val.jsonl, test.jsonl, and dataset_metadata.json."""
    os.makedirs(output_dir, exist_ok=True)
    full_samples = expand_dataset(RAW_SAMPLES, target_size=140, seed=42)
    train, val, test = split_dataset(full_samples, seed=42)

    def write_jsonl(path: str, data: List[Dict[str, Any]]):
        with open(path, "w", encoding="utf-8") as f:
            for d in data:
                f.write(json.dumps(d) + "\n")

    train_path = os.path.join(output_dir, "train.jsonl")
    val_path = os.path.join(output_dir, "val.jsonl")
    test_path = os.path.join(output_dir, "test.jsonl")

    write_jsonl(train_path, train)
    write_jsonl(val_path, val)
    write_jsonl(test_path, test)

    metadata = {
        "dataset_name": "ProofFlow Dispute & Transaction Event Dataset",
        "dataset_version": DATASET_VERSION,
        "seed": 42,
        "total_samples": len(full_samples),
        "split_counts": {
            "train": len(train),
            "val": len(val),
            "test": len(test),
        },
        "num_classes": len(ALL_EVENT_CLASSES),
        "classes": ALL_EVENT_CLASSES,
        "label2id": LABEL2ID,
    }

    meta_path = os.path.join(output_dir, "dataset_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return metadata


if __name__ == "__main__":
    meta = save_dataset_splits()
    print(json.dumps(meta, indent=2))
